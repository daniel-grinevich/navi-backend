"""Tests for the machine (Raspberry Pi) order pickup flow.

Covers the signed QR token, the atomic claim on scan/start, the claim lease,
and the complete/error paths.
"""

import time
from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.orders.api.machine_views import CLAIM_LEASE_SECONDS
from navi_backend.orders.api.serializers import OrderSerializer
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.qr import QR_MAX_AGE_SECONDS
from navi_backend.orders.qr import InvalidQrTokenError
from navi_backend.orders.qr import make_qr_token
from navi_backend.orders.qr import read_qr_token

from .factories import OrderFactory

pytestmark = pytest.mark.django_db

SCAN_URL = reverse("api:machine-order-scan")
QUEUE_URL = reverse("api:machine-order-queue")


@pytest.fixture
def pi(db):
    return RaspberryPiFactory(is_connected=True)


@pytest.fixture
def navi_port(pi):
    return NaviPortFactory(raspberry_pi=pi)


@pytest.fixture
def machine_client(pi):
    client = APIClient()
    client.credentials(HTTP_X_DEVICE_TOKEN=pi.device_token)
    return client


@pytest.fixture
def order(db):
    return OrderFactory(order_status="O", navi_port=None)


@pytest.fixture
def mock_broadcast():
    with mock.patch(
        "navi_backend.orders.api.machine_views.broadcast_order_status"
    ) as m:
        yield m


class TestQrToken:
    def test_round_trip(self, order):
        assert read_qr_token(make_qr_token(order.id)) == str(order.id)

    def test_tampered_token_rejected(self, order):
        token = make_qr_token(order.id)
        with pytest.raises(InvalidQrTokenError):
            read_qr_token(token[:-3] + "xyz")

    def test_expired_token_rejected(self, order):
        past = time.time() - QR_MAX_AGE_SECONDS - 1
        with mock.patch("django.core.signing.time.time", return_value=past):
            token = make_qr_token(order.id)
        with pytest.raises(InvalidQrTokenError):
            read_qr_token(token)

    def test_serializer_exposes_token_only_while_ordered(self, order):
        assert read_qr_token(OrderSerializer(order).data["qr_token"]) == str(order.id)

        order.order_status = "S"
        order.save(update_fields=["order_status"])
        assert OrderSerializer(order).data["qr_token"] is None


class TestScan:
    def test_scan_claims_order(
        self, machine_client, pi, navi_port, order, mock_broadcast
    ):
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )

        assert response.status_code == 200
        order.refresh_from_db()
        assert order.order_status == "S"
        assert order.navi_port == navi_port
        assert order.claimed_by == pi
        assert order.claimed_at is not None
        mock_broadcast.assert_called_once_with(order.id, "S")

    def test_missing_token(self, machine_client, navi_port):
        response = machine_client.post(SCAN_URL, {}, format="json")
        assert response.status_code == 400

    def test_bad_token(self, machine_client, navi_port):
        response = machine_client.post(
            SCAN_URL, {"qr_token": "not-a-real-token"}, format="json"
        )
        assert response.status_code == 400
        assert "invalid" in response.data["detail"].lower()

    def test_requires_device_token(self, navi_port, order):
        response = APIClient().post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )
        assert response.status_code == 401

    def test_disconnected_pi_rejected(self, pi, navi_port, order, machine_client):
        pi.is_connected = False
        pi.save(update_fields=["is_connected"])
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )
        assert response.status_code == 401

    def test_pi_without_port_rejected(self, machine_client, order):
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )
        assert response.status_code == 400
        assert "NaviPort" in response.data["detail"]


class TestClaimLock:
    def test_second_pi_cannot_steal_fresh_claim(self, navi_port, order, mock_broadcast):
        other_pi = RaspberryPiFactory(is_connected=True)
        NaviPortFactory(raspberry_pi=other_pi)
        order.order_status = "S"
        order.claimed_by = navi_port.raspberry_pi
        order.claimed_at = timezone.now()
        order.save()

        client = APIClient()
        client.credentials(HTTP_X_DEVICE_TOKEN=other_pi.device_token)
        response = client.post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )

        # The fresh claim blocks the second Pi at the atomic UPDATE.
        assert response.status_code == 409
        order.refresh_from_db()
        assert order.claimed_by == navi_port.raspberry_pi

    def test_order_routed_elsewhere_rejected(self, navi_port, order, mock_broadcast):
        other_pi = RaspberryPiFactory(is_connected=True)
        NaviPortFactory(raspberry_pi=other_pi)
        order.navi_port = navi_port
        order.save(update_fields=["navi_port"])

        client = APIClient()
        client.credentials(HTTP_X_DEVICE_TOKEN=other_pi.device_token)
        response = client.post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )

        assert response.status_code == 400
        assert "different location" in response.data["detail"]
        order.refresh_from_db()
        assert order.order_status == "O"

    def test_same_order_cannot_be_claimed_twice(
        self, machine_client, pi, navi_port, order, mock_broadcast
    ):
        token = make_qr_token(order.id)
        assert (
            machine_client.post(
                SCAN_URL, {"qr_token": token}, format="json"
            ).status_code
            == 200
        )

        response = machine_client.post(SCAN_URL, {"qr_token": token}, format="json")
        assert response.status_code == 409
        assert response.data["order_status"] == "S"

    def test_stale_claim_is_reclaimable(
        self, machine_client, pi, navi_port, order, mock_broadcast
    ):
        stale = timezone.now() - timedelta(seconds=CLAIM_LEASE_SECONDS + 1)
        order.order_status = "S"
        order.navi_port = navi_port
        order.claimed_by = pi
        order.claimed_at = stale
        order.save()

        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )

        assert response.status_code == 200
        order.refresh_from_db()
        assert order.claimed_at > stale

    def test_done_order_cannot_be_claimed(
        self, machine_client, navi_port, order, mock_broadcast
    ):
        order.order_status = "D"
        order.save(update_fields=["order_status"])
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order.id)}, format="json"
        )
        assert response.status_code == 409


class TestStart:
    def test_start_claims_by_id(
        self, machine_client, pi, navi_port, order, mock_broadcast
    ):
        url = reverse("api:machine-order-start", args=[order.id])
        response = machine_client.post(url)

        assert response.status_code == 200
        order.refresh_from_db()
        assert order.order_status == "S"
        assert order.claimed_by == pi


class TestQueue:
    def test_queue_lists_pending_and_own_in_progress(
        self, machine_client, pi, navi_port
    ):
        unrouted = OrderFactory(order_status="O", navi_port=None)
        routed_here = OrderFactory(order_status="O", navi_port=navi_port)
        mine_in_progress = OrderFactory(
            order_status="S", navi_port=navi_port, claimed_by=pi
        )
        OrderFactory(order_status="O")  # routed to another port
        OrderFactory(order_status="S", navi_port=navi_port)  # claimed by nobody/other

        response = machine_client.get(QUEUE_URL)

        assert response.status_code == 200
        ids = {o["id"] for o in response.data}
        assert ids == {
            str(unrouted.id),
            str(routed_here.id),
            str(mine_in_progress.id),
        }


class TestComplete:
    @pytest.fixture
    def claimed_order(self, pi, navi_port):
        return OrderFactory(
            order_status="S",
            navi_port=navi_port,
            claimed_by=pi,
            claimed_at=timezone.now(),
        )

    def test_complete_success(self, machine_client, claimed_order, mock_broadcast):
        url = reverse("api:machine-order-complete", args=[claimed_order.id])
        with (
            mock.patch(
                "navi_backend.orders.api.machine_views.capture_stripe_payment"
            ) as capture,
            mock.patch(
                "navi_backend.orders.api.machine_views.create_order_invoice"
            ) as invoice,
            mock.patch(
                "navi_backend.orders.api.machine_views.process_order_awards"
            ) as awards,
        ):
            response = machine_client.post(url, {"outcome": "complete"}, format="json")

        assert response.status_code == 200
        claimed_order.refresh_from_db()
        assert claimed_order.order_status == "D"
        assert claimed_order.claimed_by is None
        assert claimed_order.claimed_at is None
        capture.apply_async.assert_called_once()
        invoice.apply_async.assert_called_once()
        awards.apply_async.assert_called_once()
        mock_broadcast.assert_called_once_with(claimed_order.id, "D")

    def test_error_releases_claim(
        self, machine_client, pi, claimed_order, mock_broadcast
    ):
        url = reverse("api:machine-order-complete", args=[claimed_order.id])
        response = machine_client.post(
            url,
            {"outcome": "error", "error_message": "no beans"},
            format="json",
        )

        assert response.status_code == 200
        claimed_order.refresh_from_db()
        assert claimed_order.order_status == "O"
        assert claimed_order.claimed_by is None
        log = MachineErrorLog.objects.get(order=claimed_order)
        assert log.raspberry_pi == pi
        assert log.error_message == "no beans"
        mock_broadcast.assert_called_once_with(claimed_order.id, "O", error="no beans")

    def test_other_pi_cannot_complete(self, claimed_order, mock_broadcast):
        other_pi = RaspberryPiFactory(is_connected=True)
        client = APIClient()
        client.credentials(HTTP_X_DEVICE_TOKEN=other_pi.device_token)
        url = reverse("api:machine-order-complete", args=[claimed_order.id])

        response = client.post(url, {"outcome": "complete"}, format="json")

        assert response.status_code == 409
        claimed_order.refresh_from_db()
        assert claimed_order.order_status == "S"

    def test_unclaimed_order_cannot_be_completed(
        self, machine_client, navi_port, order, mock_broadcast
    ):
        url = reverse("api:machine-order-complete", args=[order.id])
        response = machine_client.post(url, {"outcome": "complete"}, format="json")

        assert response.status_code == 409
        order.refresh_from_db()
        assert order.order_status == "O"
        mock_broadcast.assert_not_called()

    def test_unknown_outcome_rejected(self, machine_client, claimed_order):
        url = reverse("api:machine-order-complete", args=[claimed_order.id])
        response = machine_client.post(url, {"outcome": "maybe"}, format="json")
        assert response.status_code == 400
