from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from navi_backend.payments.services import StripePaymentService
from navi_backend.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


def _event(event_type, obj):
    return {"type": event_type, "data": {"object": obj}}


class TestWebhookRouting:
    @pytest.mark.parametrize(
        "event_type",
        [
            "setup_intent.succeeded",
            "charge.refunded",
            "payment_intent.canceled",
        ],
    )
    def test_event_is_handled(self, event_type):
        event = _event(event_type, {"id": "x"})
        with (
            mock.patch("stripe.Webhook.construct_event", return_value=event),
            mock.patch.object(StripePaymentService, "handle_webhook_event") as handle,
        ):
            response = APIClient().post(
                reverse("stripe-webhook"),
                data="{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig",
            )

        assert response.status_code == 200
        handle.assert_called_once_with(event)


class TestSetupIntentSucceeded:
    def test_marks_payment_ready_and_stores_card(self):
        payment = PaymentFactory(
            status="requires_setup",
            stripe_setup_intent_id="seti_1",
            stripe_payment_method_id="",
        )

        StripePaymentService.handle_webhook_event(
            _event("setup_intent.succeeded", {"id": "seti_1", "payment_method": "pm_1"})
        )

        payment.refresh_from_db()
        assert payment.status == "ready"
        assert payment.stripe_payment_method_id == "pm_1"

    def test_late_webhook_does_not_reset_charged_payment(self):
        payment = PaymentFactory(status="succeeded", stripe_setup_intent_id="seti_1")

        StripePaymentService.handle_webhook_event(
            _event("setup_intent.succeeded", {"id": "seti_1", "payment_method": "pm_1"})
        )

        payment.refresh_from_db()
        assert payment.status == "succeeded"


class TestChargeRefunded:
    def test_full_dashboard_refund_marks_payment_refunded(self):
        payment = PaymentFactory(
            status="succeeded",
            stripe_payment_intent_id="pi_1",
            amount_received=Decimal("4.50"),
        )

        StripePaymentService.handle_webhook_event(
            _event(
                "charge.refunded",
                {
                    "id": "ch_1",
                    "payment_intent": "pi_1",
                    "amount_refunded": 450,
                    "refunded": True,
                    "refunds": {"data": [{"id": "re_dash"}]},
                },
            )
        )

        payment.refresh_from_db()
        assert payment.status == "refunded"
        assert payment.amount_refunded == Decimal("4.50")
        assert payment.stripe_refund_id == "re_dash"

    def test_partial_refund_only_records_amount(self):
        payment = PaymentFactory(status="succeeded", stripe_payment_intent_id="pi_1")

        StripePaymentService.handle_webhook_event(
            _event(
                "charge.refunded",
                {
                    "id": "ch_1",
                    "payment_intent": "pi_1",
                    "amount_refunded": 100,
                    "refunded": False,
                },
            )
        )

        payment.refresh_from_db()
        assert payment.status == "succeeded"
        assert payment.amount_refunded == Decimal("1.00")

    def test_unknown_payment_intent_is_ignored(self):
        StripePaymentService.handle_webhook_event(
            _event(
                "charge.refunded",
                {"id": "ch_1", "payment_intent": "pi_missing", "refunded": True},
            )
        )


class TestPaymentIntentEvents:
    def test_canceled_marks_payment_canceled(self):
        payment = PaymentFactory(status="ready", stripe_payment_intent_id="pi_1")

        StripePaymentService.handle_webhook_event(
            _event("payment_intent.canceled", {"id": "pi_1"})
        )

        payment.refresh_from_db()
        assert payment.status == "canceled"

    def test_late_succeeded_does_not_undo_refund(self):
        payment = PaymentFactory(status="refunded", stripe_payment_intent_id="pi_1")

        StripePaymentService.handle_webhook_event(
            _event("payment_intent.succeeded", {"id": "pi_1", "amount_received": 450})
        )

        payment.refresh_from_db()
        assert payment.status == "refunded"

    def test_failed_does_not_overwrite_succeeded(self):
        payment = PaymentFactory(status="succeeded", stripe_payment_intent_id="pi_1")

        StripePaymentService.handle_webhook_event(
            _event("payment_intent.payment_failed", {"id": "pi_1"})
        )

        payment.refresh_from_db()
        assert payment.status == "succeeded"
