"""Device event log: machine API writes, heartbeat sampling, retention."""

from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.services.events import touch_presence
from navi_backend.devices.tasks import purge_old_device_events
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.orders.qr import make_qr_token
from navi_backend.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db

SCAN_URL = reverse("api:machine-order-scan")


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


@pytest.fixture(autouse=True)
def _quiet_side_effects():
    with (
        mock.patch("navi_backend.orders.api.machine_views.broadcast_order_status"),
        mock.patch("navi_backend.orders.api.machine_views.notify_port_queue_changed"),
        mock.patch("navi_backend.orders.api.machine_views.create_order_invoice"),
        mock.patch("navi_backend.orders.api.machine_views.process_order_awards"),
    ):
        yield


@pytest.fixture
def mock_charge():
    with mock.patch(
        "navi_backend.orders.api.machine_views.StripePaymentService.charge_order"
    ) as m:
        yield m


def _types(pi):
    return list(
        pi.events.exclude(type=DeviceEvent.Type.HEARTBEAT)
        .order_by("created_at")
        .values_list("type", flat=True)
    )


class TestMachineApiEvents:
    def test_claim_and_complete(self, machine_client, pi, navi_port, mock_charge):
        order = OrderFactory(order_status="O", navi_port=navi_port)

        machine_client.post(SCAN_URL, {"qr_token": make_qr_token(order)}, format="json")
        machine_client.post(
            reverse("api:machine-order-complete", args=[order.id]),
            {"outcome": "complete"},
            format="json",
        )

        assert _types(pi) == [
            DeviceEvent.Type.ORDER_CLAIMED,
            DeviceEvent.Type.BREW_COMPLETED,
        ]
        claimed = pi.events.get(type=DeviceEvent.Type.ORDER_CLAIMED)
        assert claimed.payload == {"order_id": str(order.id), "is_test": False}

    def test_error_outcome_logs_brew_failed(
        self, machine_client, pi, navi_port, mock_charge
    ):
        order = OrderFactory(
            order_status="S",
            navi_port=navi_port,
            claimed_by=pi,
            claimed_at=timezone.now(),
        )

        machine_client.post(
            reverse("api:machine-order-complete", args=[order.id]),
            {"outcome": "error", "error_message": "grinder jammed"},
            format="json",
        )

        event = pi.events.get(type=DeviceEvent.Type.BREW_FAILED)
        assert event.message == "grinder jammed"
        assert event.payload["error_message"] == "grinder jammed"


class TestTestOrderMachineFlow:
    def test_full_loop_without_stripe_invoice_or_awards(
        self, machine_client, pi, navi_port, mock_charge
    ):
        order = OrderFactory(
            order_status="O", navi_port=navi_port, payment=None, is_test=True
        )

        scan = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )
        assert scan.status_code == 200
        mock_charge.assert_not_called()

        with (
            mock.patch(
                "navi_backend.orders.api.machine_views.create_order_invoice"
            ) as invoice,
            mock.patch(
                "navi_backend.orders.api.machine_views.process_order_awards"
            ) as awards,
        ):
            done = machine_client.post(
                reverse("api:machine-order-complete", args=[order.id]),
                {"outcome": "complete"},
                format="json",
            )

        assert done.status_code == 200
        order.refresh_from_db()
        assert order.order_status == "D"
        invoice.apply_async.assert_not_called()
        awards.apply_async.assert_not_called()


class TestPresence:
    def test_heartbeat_is_sampled(self, pi):
        # The sampling gate is an atomic cache.add; first call wins the window.
        with mock.patch(
            "navi_backend.devices.services.events.cache.add",
            side_effect=[True, False, False],
        ):
            for _ in range(3):
                touch_presence(pi.pk)

        assert pi.events.filter(type=DeviceEvent.Type.HEARTBEAT).count() == 1

    def test_firmware_header_is_recorded(self, machine_client, pi, navi_port):
        machine_client.get(
            reverse("api:machine-order-queue"), HTTP_X_FIRMWARE_VERSION="0.4.1"
        )
        pi.refresh_from_db()
        assert pi.firmware_version == "0.4.1"


class TestRetention:
    def test_purges_only_old_events(self, pi):
        old = DeviceEvent.objects.create(
            raspberry_pi=pi, type=DeviceEvent.Type.CONNECTED
        )
        DeviceEvent.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        fresh = DeviceEvent.objects.create(
            raspberry_pi=pi, type=DeviceEvent.Type.CONNECTED
        )

        assert purge_old_device_events(days=30) == 1
        assert list(DeviceEvent.objects.values_list("pk", flat=True)) == [fresh.pk]
