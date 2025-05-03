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
        print(order.price)
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

        # Update your Payment record
        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
            payment.amount_received = (
                intent.amount_received / 100
            )  # Convert back to dollars
            payment.status = intent.status
            payment.save()

            # Update the related order too, if needed
            order = payment.order
            order.status = "D"
            order.save()

        except Payment.DoesNotExist:
            # You might want to log this
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

            # Update the related order too, if needed
            order = payment.order
            order.status = "cancelled"
            order.save()

        except Payment.DoesNotExist:
            # Log this if needed
            pass

        return intent

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
