import stripe
from django.conf import settings

from navi_backend.payments.models import Payment

stripe.api_key = settings.STRIPE_API_KEY


class StripePaymentService:
    @staticmethod
    def create_payment_intent(order):
        """
        Creates a Stripe PaymentIntent with manual capture for an order.
        """
        user = StripePaymentService.get_or_create_stripe_customer(order.user)
        intent = stripe.PaymentIntent.create(
            amount=int(order.price * 100),  # Stripe expects amount in cents
            currency="usd",
            customer=user,
            capture_method="manual",  # Authorize, but don't charge yet
            automatic_payment_methods={"enabled": True},
            metadata={
                "order_id": order.id,
            },
        )

        payment = Payment.objects.create(
            stripe_payment_intent_id=intent.id,
            amount_received=0,  # Not captured yet
            status="requires_capture",
            created_by=order.user,
            updated_by=order.user,
        )

        return intent.client_secret, payment

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

        elif event_type == "payment_intent.payment_failed":
            payment.status = "failed"
            payment.save(update_fields=["status"])

            from navi_backend.orders.models import Order

            Order.objects.filter(payment=payment, order_status="O").update(
                order_status="C"
            )

        elif event_type == "payment_intent.canceled":
            payment.status = "canceled"
            payment.save(update_fields=["status"])

            from navi_backend.orders.models import Order

            Order.objects.filter(payment=payment, order_status="O").update(
                order_status="C"
            )

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
