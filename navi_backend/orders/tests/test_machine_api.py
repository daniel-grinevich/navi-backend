"""Tests for the machine (Raspberry Pi) order pickup flow.

Covers the signed QR token (nonce rotation, expiry), the atomic claim on
scan/start, the claim lease, port scoping of the queue and nudges, and the
complete/error paths.
"""

import importlib
import time
from datetime import timedelta
from unittest import mock

import pytest
import stripe
from django.core import signing
from django.urls import NoReverseMatch
from django.urls import clear_url_caches
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

import config.api_router
import config.urls
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.orders.api.machine_views import CLAIM_LEASE_SECONDS
from navi_backend.orders.api.serializers import OrderSerializer
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.qr import QR_MAX_AGE_SECONDS
from navi_backend.orders.qr import QR_SALT
from navi_backend.orders.qr import InvalidQrTokenError
from navi_backend.orders.qr import make_qr_token
from navi_backend.orders.qr import read_qr_token
from navi_backend.orders.qr import rotate_qr_nonce

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
def order(navi_port):
    return OrderFactory(order_status="O", navi_port=navi_port)


@pytest.fixture
def mock_broadcast():
    with mock.patch(
        "navi_backend.orders.api.machine_views.broadcast_order_status"
    ) as m:
        yield m


@pytest.fixture
def mock_notify():
    with mock.patch(
        "navi_backend.orders.api.machine_views.notify_port_queue_changed"
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_charge():
    """Stub the off-session charge fired at scan so tests don't hit Stripe."""
    with mock.patch(
        "navi_backend.orders.api.machine_views.StripePaymentService.charge_order"
    ) as m:
        yield m


class TestQrToken:
    def test_round_trip(self, order):
        assert read_qr_token(make_qr_token(order)) == str(order.id)

    def test_max_age_is_five_minutes(self):
        assert QR_MAX_AGE_SECONDS == 60 * 5

    def test_rotated_nonce_rejects_old_token(self, order):
        token = make_qr_token(order)
        rotate_qr_nonce(order)

        with pytest.raises(InvalidQrTokenError, match="no longer valid"):
            read_qr_token(token)
        assert read_qr_token(make_qr_token(order)) == str(order.id)

    def test_token_without_nonce_rejected(self, order):
        # Pre-nonce token format: just the signed order id.
        legacy = signing.dumps(str(order.id), salt=QR_SALT)
        with pytest.raises(InvalidQrTokenError):
            read_qr_token(legacy)

    def test_tampered_token_rejected(self, order):
        token = make_qr_token(order)
        with pytest.raises(InvalidQrTokenError):
            read_qr_token(token[:-3] + "xyz")

    def test_expired_token_rejected(self, order):
        past = time.time() - QR_MAX_AGE_SECONDS - 1
        with mock.patch("django.core.signing.time.time", return_value=past):
            token = make_qr_token(order)
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
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert response.status_code == 200
        order.refresh_from_db()
        assert order.order_status == "S"
        assert order.navi_port == navi_port
        assert order.claimed_by == pi
        assert order.claimed_at is not None
        mock_broadcast.assert_called_once_with(order.id, "S")

    def test_scan_charges_saved_card(
        self, machine_client, navi_port, order, mock_broadcast, mock_charge
    ):
        machine_client.post(SCAN_URL, {"qr_token": make_qr_token(order)}, format="json")
        # Charge fires at scan with the order now stamped to the scanning port.
        charged_order = mock_charge.call_args.args[0]
        assert charged_order.id == order.id
        assert charged_order.navi_port == navi_port

    def test_declined_card_releases_claim(
        self, machine_client, navi_port, order, mock_broadcast, mock_charge
    ):
        mock_charge.side_effect = stripe.error.CardError(
            "Your card was declined.", param=None, code="card_declined"
        )

        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert response.status_code == 402
        order.refresh_from_db()
        # Claim released, order back in the queue, no drink made.
        assert order.order_status == "O"
        assert order.claimed_by is None
        assert order.claimed_at is None
        mock_broadcast.assert_not_called()

    def test_old_token_rejected_after_claim_and_release(
        self, machine_client, order, mock_broadcast, mock_charge
    ):
        mock_charge.side_effect = stripe.error.CardError(
            "Your card was declined.", param=None, code="card_declined"
        )
        token = make_qr_token(order)
        assert (
            machine_client.post(
                SCAN_URL, {"qr_token": token}, format="json"
            ).status_code
            == 402
        )

        # The order is claimable again, but only with a freshly minted QR.
        response = machine_client.post(SCAN_URL, {"qr_token": token}, format="json")
        assert response.status_code == 400
        assert "no longer valid" in response.data["detail"]

        order.refresh_from_db()
        mock_charge.side_effect = None
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )
        assert response.status_code == 200

    def test_expired_token_rejected(self, machine_client, order):
        past = time.time() - QR_MAX_AGE_SECONDS - 1
        with mock.patch("django.core.signing.time.time", return_value=past):
            token = make_qr_token(order)

        response = machine_client.post(SCAN_URL, {"qr_token": token}, format="json")

        assert response.status_code == 400
        assert "expired" in response.data["detail"]
        order.refresh_from_db()
        assert order.order_status == "O"

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
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )
        assert response.status_code == 401

    def test_disconnected_pi_rejected(self, pi, navi_port, order, machine_client):
        pi.is_connected = False
        pi.save(update_fields=["is_connected"])
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )
        assert response.status_code == 401

    def test_pi_without_port_rejected(self, machine_client):
        order = OrderFactory(order_status="O")
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )
        assert response.status_code == 400
        assert "NaviPort" in response.data["detail"]


class TestClaimLock:
    def test_second_pi_cannot_steal_fresh_claim(
        self, pi, navi_port, order, mock_broadcast
    ):
        order.order_status = "S"
        order.claimed_by = pi
        order.claimed_at = timezone.now()
        order.save()
        # The port's Pi is swapped out mid-drink (e.g. a replacement unit).
        other_pi = RaspberryPiFactory(is_connected=True)
        navi_port.raspberry_pi = other_pi
        navi_port.save(update_fields=["raspberry_pi"])

        client = APIClient()
        client.credentials(HTTP_X_DEVICE_TOKEN=other_pi.device_token)
        response = client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        # The fresh claim blocks the second Pi at the atomic UPDATE.
        assert response.status_code == 409
        order.refresh_from_db()
        assert order.claimed_by == pi

    def test_order_routed_elsewhere_rejected(self, navi_port, order, mock_broadcast):
        other_pi = RaspberryPiFactory(is_connected=True)
        NaviPortFactory(raspberry_pi=other_pi)
        order.navi_port = navi_port
        order.save(update_fields=["navi_port"])

        client = APIClient()
        client.credentials(HTTP_X_DEVICE_TOKEN=other_pi.device_token)
        response = client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert response.status_code == 400
        assert "different location" in response.data["detail"]
        order.refresh_from_db()
        assert order.order_status == "O"

    def test_same_order_cannot_be_claimed_twice(
        self, machine_client, pi, navi_port, order, mock_broadcast
    ):
        token = make_qr_token(order)
        assert (
            machine_client.post(
                SCAN_URL, {"qr_token": token}, format="json"
            ).status_code
            == 200
        )

        # The claim rotated the nonce, so the same QR can't be replayed.
        response = machine_client.post(SCAN_URL, {"qr_token": token}, format="json")
        assert response.status_code == 400
        order.refresh_from_db()
        assert order.order_status == "S"

    def test_unrouted_order_cannot_be_claimed(
        self, machine_client, navi_port, mock_broadcast
    ):
        order = OrderFactory(order_status="O", navi_port=None)
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert response.status_code == 400
        order.refresh_from_db()
        assert order.order_status == "O"

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
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
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
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )
        assert response.status_code == 409


def _reload_urlconf():
    importlib.reload(config.api_router)
    importlib.reload(config.urls)
    clear_url_caches()


@pytest.fixture
def debug_urls(settings):
    """Rebuild the URLconf with DEBUG on, where the start route exists."""
    settings.DEBUG = True
    _reload_urlconf()
    yield
    settings.DEBUG = False
    _reload_urlconf()


class TestStart:
    def test_start_route_absent_without_debug(self, machine_client, order):
        with pytest.raises(NoReverseMatch):
            reverse("api:machine-order-start", args=[order.id])

        response = machine_client.post(f"/api/machine/orders/{order.id}/start/")

        assert response.status_code == 404
        order.refresh_from_db()
        assert order.order_status == "O"

    @pytest.mark.usefixtures("debug_urls")
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
        OrderFactory(order_status="O", navi_port=None)  # unrouted: never listed
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
            str(routed_here.id),
            str(mine_in_progress.id),
        }


class TestPresence:
    def test_machine_request_touches_last_seen(self, machine_client, pi, navi_port):
        pi.last_seen = None
        pi.save(update_fields=["last_seen"])

        response = machine_client.get(QUEUE_URL)

        assert response.status_code == 200
        pi.refresh_from_db()
        assert pi.last_seen is not None

    def test_scan_nudges_machines(
        self, machine_client, navi_port, order, mock_broadcast, mock_notify
    ):
        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert response.status_code == 200
        mock_notify.assert_called_once_with(navi_port)

    def test_failed_claim_does_not_nudge(
        self, machine_client, navi_port, order, mock_broadcast, mock_notify
    ):
        order.order_status = "D"
        order.save(update_fields=["order_status"])

        response = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert response.status_code == 409
        mock_notify.assert_not_called()


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
        nonce_before = claimed_order.qr_nonce
        url = reverse("api:machine-order-complete", args=[claimed_order.id])
        with (
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
        assert claimed_order.qr_nonce != nonce_before
        assert claimed_order.claimed_by is None
        assert claimed_order.claimed_at is None
        # Payment was already taken at scan; completion no longer captures.
        invoice.apply_async.assert_called_once()
        awards.apply_async.assert_called_once()
        mock_broadcast.assert_called_once_with(claimed_order.id, "D")

    def test_error_releases_claim(
        self, machine_client, pi, claimed_order, mock_broadcast
    ):
        nonce_before = claimed_order.qr_nonce
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
        assert claimed_order.qr_nonce != nonce_before
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
