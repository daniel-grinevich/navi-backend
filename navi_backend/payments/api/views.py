import logging

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from navi_backend.orders.api.mixins import TrackUserMixin
from navi_backend.payments.api.serializers import PaymentCreateSerializer
from navi_backend.payments.api.serializers import PaymentSerializer
from navi_backend.payments.models import Payment
from navi_backend.payments.services import StripePaymentService

logger = logging.getLogger(__name__)


class PaymentViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentCreateSerializer
        return PaymentSerializer


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    """
    Receives Stripe webhook events and updates payment/order state.
    Verifies the webhook signature using STRIPE_WEBHOOK_SECRET.
    """

    HANDLED_EVENTS = {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled",
    }

    def post(self, request):
        payload = request.body
        sig_header = request.headers.get("stripe-signature", "")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            logger.warning("Stripe webhook: invalid payload")
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError:
            logger.warning("Stripe webhook: invalid signature")
            return HttpResponse(status=400)

        if event["type"] in self.HANDLED_EVENTS:
            StripePaymentService.handle_webhook_event(event)

        return HttpResponse(status=200)
