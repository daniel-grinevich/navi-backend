import logging

from celery import shared_task

from navi_backend.payments.services import StripePaymentService

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def capture_stripe_payment(self, payment_intent_id):
    """Capture a previously authorized PaymentIntent out of the request path."""
    StripePaymentService.capture_payment(payment_intent_id)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def cancel_stripe_payment(self, payment_intent_id):
    """Cancel an authorized PaymentIntent out of the request path."""
    StripePaymentService.cancel_payment(payment_intent_id)
