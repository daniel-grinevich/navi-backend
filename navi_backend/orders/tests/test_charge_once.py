"""Charge-exactly-once + refund scenarios for the machine pickup flow.

Stripe is mocked at the client boundary (``stripe.PaymentIntent.create``,
``stripe.Refund.create``), so the real scan/complete views, services and
payment bookkeeping run end to end against real (committed) transactions.
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
import stripe
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.qr import make_qr_token
from navi_backend.orders.services.scan_order_service import CLAIM_LEASE_SECONDS
from navi_backend.payments.models import EffectiveTaxRate
from navi_backend.payments.tests.factories import PaymentFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import OrderFactory
from .factories import OrderItemFactory

# Real commits: the views are non-atomic and the services commit per step.
pytestmark = pytest.mark.django_db(transaction=True)

SCAN_URL = reverse("api:machine-order-scan")


def _complete_url(order):
    return reverse("api:machine-order-complete", args=[order.id])


def _refund_url(order):
    return reverse("api:admin-orders-refund", args=[order.id])


def _intent(order_id="", status="succeeded", amount=450):
    return SimpleNamespace(
        id=f"pi_{order_id}"[:30], status=status, amount_received=amount
    )


@pytest.fixture
def pi(db):
    return RaspberryPiFactory(is_connected=True)


@pytest.fixture
def navi_port(pi):
    port = NaviPortFactory(raspberry_pi=pi)
    # Cached 0% rate: the charge is exactly the $4.50 subtotal, no tax API.
    EffectiveTaxRate.objects.create(
        navi_port=port, rate=Decimal("0.0000"), effective_date=timezone.localdate()
    )
    return port


@pytest.fixture
def machine_client(pi):
    client = APIClient()
    client.credentials(HTTP_X_DEVICE_TOKEN=pi.device_token)
    return client


@pytest.fixture
def order(navi_port):
    payment = PaymentFactory(
        status="ready",
        stripe_payment_intent_id=None,
        stripe_payment_method_id="pm_saved",
        amount_received=Decimal("0.00"),
    )
    order = OrderFactory(
        order_status="O",
        navi_port=navi_port,
        payment=payment,
        user=UserFactory(stripe_customer_id="cus_123"),
    )
    OrderItemFactory(order=order, quantity=1, unit_price=Decimal("4.50"))
    return order


@pytest.fixture
def stripe_charge(order):
    with mock.patch(
        "stripe.PaymentIntent.create", return_value=_intent(order.id.hex)
    ) as m:
        yield m


@pytest.fixture
def stripe_refund():
    with mock.patch(
        "stripe.Refund.create",
        return_value=SimpleNamespace(id="re_123", amount=450, status="succeeded"),
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def quiet_tasks():
    """Don't enqueue real Celery work from the code under test."""
    with (
        mock.patch("navi_backend.payments.tasks.record_stripe_tax_transaction"),
        mock.patch("navi_backend.orders.api.machine_views.create_order_invoice"),
        mock.patch("navi_backend.orders.api.machine_views.process_order_awards"),
        mock.patch("navi_backend.orders.services.fail_order_service.refund_order"),
    ):
        yield


def _scan(client, order):
    return client.post(SCAN_URL, {"qr_token": make_qr_token(order)}, format="json")


def _fail(client, order, message="grinder jammed"):
    return client.post(
        _complete_url(order),
        {"outcome": "error", "error_message": message},
        format="json",
    )


class TestChargeOnce:
    def test_scan_charges_with_idempotency_key(
        self, machine_client, order, stripe_charge
    ):
        response = _scan(machine_client, order)

        assert response.status_code == 200
        stripe_charge.assert_called_once()
        kwargs = stripe_charge.call_args.kwargs
        assert kwargs["idempotency_key"] == f"order-{order.id}-charge"
        assert kwargs["amount"] == 450
        order.payment.refresh_from_db()
        assert order.payment.status == "succeeded"
        assert order.payment.amount_received == Decimal("4.50")

    def test_stale_lease_reclaim_does_not_charge_again(
        self, machine_client, pi, order, stripe_charge
    ):
        assert _scan(machine_client, order).status_code == 200
        # The Pi dies mid-brew: no complete, and the lease goes stale.
        order.refresh_from_db()
        order.claimed_at = timezone.now() - timedelta(seconds=CLAIM_LEASE_SECONDS + 1)
        order.save(update_fields=["claimed_at"])

        response = _scan(machine_client, order)

        assert response.status_code == 200
        stripe_charge.assert_called_once()  # still just the first charge
        order.refresh_from_db()
        assert order.order_status == "S"
        assert order.payment.status == "succeeded"
        # The abandoned claim is visible to staff.
        assert MachineErrorLog.objects.filter(order=order).count() == 1

    def test_failure_after_charge_keeps_the_charge(
        self, machine_client, order, stripe_charge
    ):
        """B4b: a crash after Stripe succeeded must not roll back the charge."""
        with mock.patch(
            "navi_backend.orders.api.machine_views.MachineOrderSerializer",
            side_effect=RuntimeError("serializer blew up"),
        ):
            client = APIClient(raise_request_exception=False)
            client.credentials(**machine_client._credentials)
            response = _scan(client, order)
        assert response.status_code == 500

        order.refresh_from_db()
        order.payment.refresh_from_db()
        # Claim and charge are committed; nothing points back at "O".
        assert order.order_status == "S"
        assert order.payment.status == "succeeded"
        assert order.payment.stripe_payment_intent_id

        # Once the lease is stale the retry reclaims without a second charge.
        order.claimed_at = timezone.now() - timedelta(seconds=CLAIM_LEASE_SECONDS + 1)
        order.save(update_fields=["claimed_at"])
        assert _scan(machine_client, order).status_code == 200
        stripe_charge.assert_called_once()

    def test_broadcast_failure_after_charge_is_not_a_500(
        self, machine_client, order, stripe_charge
    ):
        """A Redis blip in the post-commit broadcast mustn't fail the scan."""
        with mock.patch(
            "navi_backend.orders.services.scan_order_service.broadcast_order_status",
            side_effect=ConnectionError("redis down"),
        ):
            response = _scan(machine_client, order)

        assert response.status_code == 200
        order.payment.refresh_from_db()
        assert order.payment.status == "succeeded"

    def test_stripe_error_after_charge_retries_with_same_key(
        self, machine_client, order
    ):
        """B5: Stripe charged but the client raised -> retry reuses the key."""
        with mock.patch(
            "stripe.PaymentIntent.create",
            side_effect=[
                stripe.error.APIConnectionError("connection reset"),
                _intent(order.id.hex),
            ],
        ) as create:
            first = _scan(machine_client, order)
            assert first.status_code == 402
            order.refresh_from_db()
            assert order.order_status == "O"  # released for a retry

            second = _scan(machine_client, order)

        assert second.status_code == 200
        keys = [c.kwargs["idempotency_key"] for c in create.call_args_list]
        # Same key both times: Stripe returns the original PaymentIntent
        # instead of creating a second charge.
        assert keys == [f"order-{order.id}-charge"] * 2

    def test_order_without_payment_is_402_not_500(self, machine_client, order):
        order.payment = None
        order.save(update_fields=["payment"])

        response = _scan(machine_client, order)

        assert response.status_code == 402
        order.refresh_from_db()
        assert order.order_status == "O"


class TestMachineErrorRefund:
    def test_error_after_charge_refunds_and_cancels(
        self, machine_client, pi, order, stripe_charge, stripe_refund
    ):
        assert _scan(machine_client, order).status_code == 200

        response = _fail(machine_client, order)

        assert response.status_code == 200
        assert response.data == {"ok": True, "order_status": "C", "refunded": True}
        stripe_refund.assert_called_once()
        kwargs = stripe_refund.call_args.kwargs
        assert kwargs["idempotency_key"] == f"order-{order.id}-refund"
        assert kwargs["payment_intent"] == stripe_charge.return_value.id

        order.refresh_from_db()
        order.payment.refresh_from_db()
        assert order.order_status == "C"
        assert order.cancel_reason == "Machine error: grinder jammed"
        assert order.claimed_by is None
        assert order.payment.status == "refunded"
        assert order.payment.stripe_refund_id == "re_123"
        assert order.payment.amount_refunded == Decimal("4.50")
        log = MachineErrorLog.objects.get(order=order)
        assert log.raspberry_pi == pi
        assert log.error_message == "grinder jammed"

    def test_rescan_after_refund_is_rejected_without_charging(
        self, machine_client, order, stripe_charge, stripe_refund
    ):
        _scan(machine_client, order)
        _fail(machine_client, order)

        # The cancel rotated the QR nonce, so the scanned code is dead...
        assert _scan(machine_client, order).status_code == 400
        # ...and even a freshly minted token can't restart a cancelled order.
        order.refresh_from_db()
        response = _scan(machine_client, order)

        assert response.status_code == 409
        assert response.data["order_status"] == "C"
        stripe_charge.assert_called_once()

    def test_refund_failure_keeps_order_cancelled_and_queues_retry(
        self, machine_client, order, stripe_charge
    ):
        _scan(machine_client, order)
        with (
            mock.patch(
                "stripe.Refund.create",
                side_effect=stripe.error.APIConnectionError("stripe down"),
            ),
            mock.patch(
                "navi_backend.orders.services.fail_order_service.refund_order"
            ) as retry,
        ):
            response = _fail(machine_client, order)

        assert response.status_code == 200
        assert response.data["refunded"] is False
        order.refresh_from_db()
        order.payment.refresh_from_db()
        assert order.order_status == "C"
        assert order.payment.status == "succeeded"  # still refundable by staff
        retry.apply_async.assert_called_once_with(
            args=[str(order.id), "Machine error: grinder jammed"]
        )

    def test_error_on_uncharged_order_cancels_without_refund(
        self, machine_client, pi, order, stripe_refund
    ):
        order.order_status = "S"
        order.claimed_by = pi
        order.claimed_at = timezone.now()
        order.save()

        response = _fail(machine_client, order)

        assert response.status_code == 200
        assert response.data["refunded"] is False
        stripe_refund.assert_not_called()
        order.refresh_from_db()
        assert order.order_status == "C"


class TestAdminRefund:
    @pytest.fixture
    def admin_client(self, admin_user):
        client = APIClient()
        client.force_authenticate(admin_user)
        return client

    @pytest.fixture
    def charged_order(self, machine_client, order, stripe_charge):
        _scan(machine_client, order)
        order.refresh_from_db()
        return order

    def test_refunds_charged_order(self, admin_client, charged_order, stripe_refund):
        response = admin_client.post(
            _refund_url(charged_order), {"reason": "cold coffee"}, format="json"
        )

        assert response.status_code == 200
        assert response.data == {
            "order_id": str(charged_order.id),
            "order_status": "C",
            "payment_status": "refunded",
            "refund_id": "re_123",
            "amount": "4.50",
        }
        assert stripe_refund.call_args.kwargs["idempotency_key"] == (
            f"order-{charged_order.id}-refund"
        )
        charged_order.refresh_from_db()
        assert charged_order.order_status == "C"
        assert charged_order.cancel_reason == "cold coffee"

    def test_already_refunded_is_409(self, admin_client, charged_order, stripe_refund):
        admin_client.post(_refund_url(charged_order), {"reason": "x"}, format="json")

        response = admin_client.post(
            _refund_url(charged_order), {"reason": "x"}, format="json"
        )

        assert response.status_code == 409
        assert response.data["error"]["code"] == 409
        stripe_refund.assert_called_once()

    def test_uncharged_order_is_409(self, admin_client, order, stripe_refund):
        response = admin_client.post(_refund_url(order), {"reason": "x"}, format="json")

        assert response.status_code == 409
        stripe_refund.assert_not_called()

    def test_reason_required(self, admin_client, charged_order, stripe_refund):
        response = admin_client.post(_refund_url(charged_order), {}, format="json")

        assert response.status_code == 400
        stripe_refund.assert_not_called()

    def test_non_staff_forbidden(self, order, stripe_refund):
        client = APIClient()
        client.force_authenticate(order.user)

        response = client.post(_refund_url(order), {"reason": "x"}, format="json")

        assert response.status_code == 403
        stripe_refund.assert_not_called()
