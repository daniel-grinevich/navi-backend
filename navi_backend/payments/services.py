from decimal import ROUND_HALF_UP
from decimal import Decimal

import stripe
from django.conf import settings
from django.utils import timezone

from navi_backend.core.logging import get_logger
from navi_backend.payments.models import EffectiveTaxRate
from navi_backend.payments.models import Payment

stripe.api_key = settings.STRIPE_API_KEY

logger = get_logger(__name__)


class StripePaymentService:
    @staticmethod
    def create_setup_intent(order):
        """
        Save the customer's card at checkout via a SetupIntent, for an
        off-session charge at pickup.

        No money moves and no tax is calculated here: the pickup NaviPort (and
        therefore the tax jurisdiction) isn't final until the order is scanned
        at a machine, so the actual charge happens then via ``charge_order``.
        """
        customer = StripePaymentService.get_or_create_stripe_customer(order.user)

        intent = stripe.SetupIntent.create(
            customer=customer,
            usage="off_session",
            automatic_payment_methods={"enabled": True},
            metadata={"order_id": order.id},
        )

        payment = Payment.objects.create(
            stripe_setup_intent_id=intent.id,
            status="requires_setup",
            created_by=order.user,
            updated_by=order.user,
        )

        logger.info(
            "setup_intent_created",
            order_id=order.id,
            setup_intent_id=intent.id,
        )
        return intent.client_secret, payment

    @staticmethod
    def charge_order(order):
        """
        Charge the saved card off-session for the exact subtotal + tax at the
        actual pickup NaviPort. Called at scan, before the drink is made.

        Raises ``stripe.error.CardError`` if the off-session charge is declined
        or needs authentication, so the caller can refuse to start the order.
        """
        payment = order.payment
        customer = StripePaymentService.get_or_create_stripe_customer(order.user)
        payment_method = StripePaymentService._resolve_payment_method(payment)
        tax = StripePaymentService.calculate_tax(order)

        intent = stripe.PaymentIntent.create(
            amount=tax["total_cents"],
            currency="usd",
            customer=customer,
            payment_method=payment_method,
            off_session=True,
            confirm=True,
            metadata={
                "order_id": order.id,
                "tax_calculation_id": tax["calculation_id"] or "",
            },
        )

        payment.stripe_payment_intent_id = intent.id
        payment.stripe_payment_method_id = payment_method
        payment.subtotal = tax["subtotal"]
        payment.tax_amount = tax["tax_amount"]
        payment.total_amount = tax["total"]
        payment.stripe_tax_calculation_id = tax["calculation_id"] or ""
        payment.amount_received = Decimal(intent.amount_received) / 100
        payment.status = intent.status
        payment.save()

        logger.info(
            "order_charged",
            order_id=order.id,
            payment_intent_id=intent.id,
            amount_received=payment.amount_received,
            status=intent.status,
        )

        if intent.status == "succeeded":
            # Record the sale to Stripe Tax for filing off the scan critical
            # path (a local import avoids a tasks <-> services import cycle).
            from navi_backend.payments.tasks import (  # noqa: PLC0415
                record_stripe_tax_transaction,
            )

            record_stripe_tax_transaction.apply_async(args=[str(order.id)])

        return intent

    @staticmethod
    def _resolve_payment_method(payment):
        """
        The payment method saved by the checkout SetupIntent. Cached on the
        Payment after the first lookup so a retried scan doesn't re-fetch it.
        """
        if payment.stripe_payment_method_id:
            return payment.stripe_payment_method_id

        setup_intent = stripe.SetupIntent.retrieve(payment.stripe_setup_intent_id)
        if not setup_intent.payment_method:
            msg = "No saved card is available for this order."
            raise ValueError(msg)

        payment.stripe_payment_method_id = setup_intent.payment_method
        payment.save(update_fields=["stripe_payment_method_id"])
        return setup_intent.payment_method

    @staticmethod
    def calculate_tax(order):
        """
        Tax owed on an order, computed from the cached rate for the pickup
        NaviPort's jurisdiction (refreshed nightly from TaxJar) so the scan-time
        charge doesn't call a tax API.

        Falls back to a live Stripe Tax calculation if the port has no cached
        rate yet (e.g. a brand-new port before the nightly job runs), and to
        zero tax if there's no jurisdiction to source at all.
        """
        subtotal = order.price

        rate = EffectiveTaxRate.current_rate(order.navi_port, timezone.localdate())
        if rate is not None:
            tax_amount = (subtotal * rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total = subtotal + tax_amount
            return {
                "subtotal": subtotal,
                "tax_amount": tax_amount,
                "total": total,
                "total_cents": int(total * 100),
                "calculation_id": None,
            }

        return StripePaymentService._live_tax_calculation(order, subtotal)

    @staticmethod
    def _live_tax_calculation(order, subtotal):
        """Fallback: compute tax with a live Stripe Tax calculation."""
        subtotal_cents = int(subtotal * 100)

        address = StripePaymentService._navi_port_tax_address(order.navi_port)
        if address is None:
            return {
                "subtotal": subtotal,
                "tax_amount": Decimal("0.00"),
                "total": subtotal,
                "total_cents": subtotal_cents,
                "calculation_id": None,
            }

        calculation = stripe.tax.Calculation.create(
            currency="usd",
            line_items=[
                {
                    "amount": subtotal_cents,
                    "reference": str(order.id),
                    "tax_behavior": "exclusive",
                }
            ],
            customer_details={
                "address": address,
                "address_source": "shipping",
            },
        )

        return {
            "subtotal": subtotal,
            "tax_amount": Decimal(calculation.tax_amount_exclusive) / 100,
            "total": Decimal(calculation.amount_total) / 100,
            "total_cents": calculation.amount_total,
            "calculation_id": calculation.id,
        }

    @staticmethod
    def _navi_port_tax_address(navi_port):
        """
        Build a Stripe address dict from a NaviPort. Country + postal code are
        the minimum Stripe needs to resolve a US jurisdiction; without a postal
        code we can't compute tax, so return None to fall back to zero tax.
        """
        if navi_port is None or not navi_port.postal_code:
            return None

        address = {
            "country": navi_port.country or "US",
            "postal_code": navi_port.postal_code,
        }
        if navi_port.address_line_1:
            address["line1"] = navi_port.address_line_1
        if navi_port.address_line_2:
            address["line2"] = navi_port.address_line_2
        if navi_port.city:
            address["city"] = navi_port.city
        if navi_port.state_or_region:
            address["state"] = navi_port.state_or_region
        return address

    @staticmethod
    def record_tax_transaction(order_id):
        """
        Record a completed sale to Stripe Tax so it shows up in tax reporting.

        Runs asynchronously after the scan-time charge (off the critical path).
        Idempotent: a no-op if the order isn't charged, has no jurisdiction, or
        was already recorded.
        """
        from navi_backend.orders.models import Order  # noqa: PLC0415

        try:
            order = Order.objects.select_related("payment", "navi_port").get(
                id=order_id
            )
        except Order.DoesNotExist:
            return

        payment = order.payment
        if (
            not payment
            or payment.status != "succeeded"
            or payment.stripe_tax_transaction_id
        ):
            return

        address = StripePaymentService._navi_port_tax_address(order.navi_port)
        if address is None:
            return

        calculation = stripe.tax.Calculation.create(
            currency="usd",
            line_items=[
                {
                    "amount": int(payment.subtotal * 100),
                    "reference": str(order.id),
                    "tax_behavior": "exclusive",
                }
            ],
            customer_details={"address": address, "address_source": "shipping"},
        )
        transaction = stripe.tax.Transaction.create_from_calculation(
            calculation=calculation.id,
            reference=payment.stripe_payment_intent_id,
        )
        payment.stripe_tax_calculation_id = calculation.id
        payment.stripe_tax_transaction_id = transaction.id
        payment.save(
            update_fields=["stripe_tax_calculation_id", "stripe_tax_transaction_id"]
        )

    @staticmethod
    def cancel_setup_intent(setup_intent_id):
        """
        Cancel the checkout SetupIntent when an order is cancelled before
        pickup. No money has moved yet, so there is nothing to refund.
        """
        intent = stripe.SetupIntent.cancel(setup_intent_id)

        try:
            payment = Payment.objects.get(stripe_setup_intent_id=setup_intent_id)
            payment.status = "canceled"
            payment.save(update_fields=["status"])
            logger.info("setup_intent_canceled", setup_intent_id=setup_intent_id)
        except Payment.DoesNotExist:
            pass

        return intent

    @staticmethod
    def handle_webhook_event(event):
        """
        Process a verified Stripe webhook event and update local state.
        """
        event_type = event["type"]
        obj = event["data"]["object"]

        if event_type == "setup_intent.succeeded":
            StripePaymentService._handle_setup_succeeded(obj)
            return

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=obj["id"])
        except Payment.DoesNotExist:
            return

        if event_type == "payment_intent.succeeded":
            payment.status = "succeeded"
            payment.amount_received = obj["amount_received"] / 100
            payment.save(update_fields=["status", "amount_received"])
            logger.info(
                "payment_succeeded",
                payment_intent_id=obj["id"],
                amount_received=payment.amount_received,
            )

        elif event_type == "payment_intent.payment_failed":
            payment.status = "failed"
            payment.save(update_fields=["status"])
            logger.warning("payment_failed", payment_intent_id=obj["id"])

    @staticmethod
    def _handle_setup_succeeded(setup_intent):
        """Store the saved card once the checkout SetupIntent completes."""
        try:
            payment = Payment.objects.get(stripe_setup_intent_id=setup_intent["id"])
        except Payment.DoesNotExist:
            return

        payment.status = "ready"
        if setup_intent.get("payment_method"):
            payment.stripe_payment_method_id = setup_intent["payment_method"]
        payment.save(update_fields=["status", "stripe_payment_method_id"])

    @staticmethod
    def get_or_create_stripe_customer(user):
        if user.stripe_customer_id:
            return user.stripe_customer_id

        customer = stripe.Customer.create(
            email=user.email, metadata={"user_id": user.id}
        )

        user.stripe_customer_id = customer.id
        user.save(update_fields=["stripe_customer_id"])

        return customer.id
