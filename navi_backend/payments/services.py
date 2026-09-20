from decimal import Decimal

import stripe
from django.conf import settings

from navi_backend.core.logging import get_logger
from navi_backend.orders.models import Order
from navi_backend.orders.utils import notify_machines_queue_changed
from navi_backend.payments.models import Payment

stripe.api_key = settings.STRIPE_API_KEY

logger = get_logger(__name__)


class StripePaymentService:
    @staticmethod
    def create_payment_intent(order):
        """
        Creates a Stripe PaymentIntent with manual capture for an order.

        Tax is calculated dynamically by Stripe Tax from the pickup NaviPort's
        address, so the amount authorized is the subtotal plus jurisdiction tax.
        """
        user = StripePaymentService.get_or_create_stripe_customer(order.user)
        tax = StripePaymentService.calculate_tax(order)

        intent = stripe.PaymentIntent.create(
            amount=tax["total_cents"],  # Stripe expects amount in cents
            currency="usd",
            customer=user,
            capture_method="manual",  # Authorize, but don't charge yet
            automatic_payment_methods={"enabled": True},
            metadata={
                "order_id": order.id,
                "tax_calculation_id": tax["calculation_id"] or "",
            },
        )

        payment = Payment.objects.create(
            stripe_payment_intent_id=intent.id,
            amount_received=0,  # Not captured yet
            subtotal=tax["subtotal"],
            tax_amount=tax["tax_amount"],
            total_amount=tax["total"],
            stripe_tax_calculation_id=tax["calculation_id"] or "",
            status="requires_capture",
            created_by=order.user,
            updated_by=order.user,
        )

        logger.info(
            "payment_intent_created",
            order_id=order.id,
            payment_intent_id=intent.id,
            amount_cents=tax["total_cents"],
        )
        return intent.client_secret, payment

    @staticmethod
    def calculate_tax(order):
        """
        Ask Stripe Tax for the tax owed on an order, sourced from the pickup
        NaviPort's address. Falls back to zero tax when the port has no address
        to compute a jurisdiction from.
        """
        subtotal = order.price
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
    def _record_tax_transaction(payment):
        """
        Convert the authorization-time tax calculation into a recorded Stripe
        Tax transaction so the sale shows up in Stripe's tax reporting. No-op if
        there was no calculation or it was already recorded.
        """
        if not payment.stripe_tax_calculation_id or payment.stripe_tax_transaction_id:
            return

        transaction = stripe.tax.Transaction.create_from_calculation(
            calculation=payment.stripe_tax_calculation_id,
            reference=payment.stripe_payment_intent_id,
        )
        payment.stripe_tax_transaction_id = transaction.id
        payment.save(update_fields=["stripe_tax_transaction_id"])

    @staticmethod
    def capture_payment(payment_intent_id):
        """
        Captures a previously authorized PaymentIntent.
        """
        intent = stripe.PaymentIntent.capture(payment_intent_id)

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
            payment.amount_received = (
                intent.amount_received / 100
            )  # Convert back to dollars
            payment.status = intent.status
            payment.save()
            StripePaymentService._record_tax_transaction(payment)
            logger.info(
                "payment_captured",
                payment_intent_id=payment_intent_id,
                amount_received=payment.amount_received,
            )
        except Payment.DoesNotExist:
            pass

        return intent

    @staticmethod
    def cancel_payment(payment_intent_id):
        """
        Cancels a PaymentIntent if the order is not fulfilled.
        """
        intent = stripe.PaymentIntent.cancel(payment_intent_id)

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
            payment.status = intent.status
            payment.save()
            logger.info("payment_canceled", payment_intent_id=payment_intent_id)
        except Payment.DoesNotExist:
            pass

        return intent

    @staticmethod
    def handle_webhook_event(event):
        """
        Process a verified Stripe webhook event and update local state.
        """
        event_type = event["type"]
        payment_intent = event["data"]["object"]
        payment_intent_id = payment_intent["id"]

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
        except Payment.DoesNotExist:
            return

        if event_type == "payment_intent.succeeded":
            payment.status = "succeeded"
            payment.amount_received = payment_intent["amount_received"] / 100
            payment.save(update_fields=["status", "amount_received"])
            StripePaymentService._record_tax_transaction(payment)
            logger.info(
                "payment_succeeded",
                payment_intent_id=payment_intent_id,
                amount_received=payment.amount_received,
            )

        elif event_type == "payment_intent.payment_failed":
            payment.status = "failed"
            payment.save(update_fields=["status"])
            logger.warning("payment_failed", payment_intent_id=payment_intent_id)
            cancelled = Order.objects.filter(payment=payment, order_status="O").update(
                order_status="C"
            )
            if cancelled:
                notify_machines_queue_changed()

        elif event_type == "payment_intent.canceled":
            payment.status = "canceled"
            payment.save(update_fields=["status"])
            cancelled = Order.objects.filter(payment=payment, order_status="O").update(
                order_status="C"
            )
            if cancelled:
                notify_machines_queue_changed()

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
