"""Maintenance mode + per-machine menu enforced at order create and at scan."""

from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.devices.tests.factories import EspressoMachineFactory
from navi_backend.devices.tests.factories import MachineTypeFactory
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.models import Order
from navi_backend.orders.qr import make_qr_token
from navi_backend.payments.tests.factories import PaymentFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import OrderFactory

pytestmark = pytest.mark.django_db

ORDERS_URL = "/api/orders/"
SCAN_URL = reverse("api:machine-order-scan")
PAUSED = "This machine isn't taking orders right now"


@pytest.fixture
def client():
    api_client = APIClient()
    api_client.force_authenticate(UserFactory())
    return api_client


@pytest.fixture
def latte():
    return MenuItemFactory(name="Latte", slug="latte", status="A", price="4.00")


@pytest.fixture
def tea():
    return MenuItemFactory(name="Tea", slug="tea", status="A", price="3.00")


@pytest.fixture
def pi():
    return RaspberryPiFactory(is_connected=True, last_seen=timezone.now())


@pytest.fixture
def port(pi, latte):
    machine_type = MachineTypeFactory()
    machine_type.supported_drinks.add(latte)
    return NaviPortFactory(
        raspberry_pi=pi,
        espresso_machine=EspressoMachineFactory(machine_type=machine_type),
    )


@pytest.fixture
def mock_setup_intent():
    with mock.patch(
        "navi_backend.orders.services.create_order_service."
        "StripePaymentService.create_setup_intent",
        side_effect=lambda order: ("secret", PaymentFactory()),
    ) as m:
        yield m


def order_payload(port, *items):
    return {
        "navi_port": str(port.id),
        "items": [{"menu_item": str(item.id), "quantity": 1} for item in items],
    }


class TestOrderCreate:
    def test_accepting_port_creates_order(self, client, port, latte, mock_setup_intent):
        resp = client.post(ORDERS_URL, order_payload(port, latte), format="json")

        assert resp.status_code == 201, resp.data
        assert Order.objects.filter(navi_port=port).count() == 1

    def test_paused_port_rejected(self, client, port, latte):
        port.accepting_orders = False
        port.save()

        resp = client.post(ORDERS_URL, order_payload(port, latte), format="json")

        assert resp.status_code == 400
        assert resp.data == {"error": {"code": 400, "message": {"navi_port": [PAUSED]}}}
        assert not Order.objects.exists()

    def test_offline_port_rejected(self, client, port, pi, latte):
        pi.last_seen = timezone.now() - timedelta(minutes=5)
        pi.save()

        resp = client.post(ORDERS_URL, order_payload(port, latte), format="json")

        assert resp.status_code == 400
        assert resp.data["error"]["message"] == {"navi_port": [PAUSED]}

    def test_unsupported_drink_rejected(self, client, port, latte, tea):
        resp = client.post(ORDERS_URL, order_payload(port, latte, tea), format="json")

        assert resp.status_code == 400
        assert resp.data["error"]["message"] == {
            "items": ["This machine can't make: Tea"]
        }
        assert not Order.objects.exists()

    def test_unrestricted_machine_accepts_any_drink(
        self, client, port, tea, mock_setup_intent
    ):
        port.espresso_machine.machine_type.supported_drinks.clear()

        resp = client.post(ORDERS_URL, order_payload(port, tea), format="json")

        assert resp.status_code == 201, resp.data


class TestScanWhilePaused:
    @pytest.fixture
    def machine_client(self, pi):
        api_client = APIClient()
        api_client.credentials(HTTP_X_DEVICE_TOKEN=pi.device_token)
        return api_client

    @pytest.fixture(autouse=True)
    def mock_side_effects(self):
        base = "navi_backend.orders.api.machine_views"
        with (
            mock.patch(f"{base}.StripePaymentService.charge_order") as charge,
            mock.patch(f"{base}.broadcast_order_status"),
            mock.patch(f"{base}.notify_port_queue_changed"),
        ):
            yield charge

    def test_paused_port_rejects_scan(self, machine_client, port, mock_side_effects):
        port.accepting_orders = False
        port.status_message = "Descaling"
        port.save()
        order = OrderFactory(order_status="O", navi_port=port)

        resp = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert resp.status_code == 409
        assert resp.data["code"] == "port_paused"
        assert resp.data["detail"] == PAUSED
        assert resp.data["status_message"] == "Descaling"
        order.refresh_from_db()
        assert order.order_status == "O"
        mock_side_effects.assert_not_called()

    def test_accepting_port_scans(self, machine_client, port):
        order = OrderFactory(order_status="O", navi_port=port)

        resp = machine_client.post(
            SCAN_URL, {"qr_token": make_qr_token(order)}, format="json"
        )

        assert resp.status_code == 200
