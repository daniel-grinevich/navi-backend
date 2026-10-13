"""Tests for the staff device-fleet API (/api/admin/devices/)."""

from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.devices.managers import hash_device_token
from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.models import Order
from navi_backend.orders.qr import read_qr_token
from navi_backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = reverse("api:admin-devices-list")
QUEUE_URL = reverse("api:machine-order-queue")


def detail_url(pi):
    return reverse("api:admin-devices-detail", args=[pi.pk])


def action_url(pi, name):
    return reverse(f"api:admin-devices-{name}", args=[pi.pk])


@pytest.fixture
def staff():
    return UserFactory(is_staff=True)


@pytest.fixture
def admin_client(staff):
    client = APIClient()
    client.force_authenticate(staff)
    return client


@pytest.fixture
def pi(db):
    return RaspberryPiFactory(is_connected=True)


@pytest.fixture
def navi_port(pi):
    return NaviPortFactory(raspberry_pi=pi)


@pytest.fixture(autouse=True)
def mock_channel_layer():
    """Websocket fan-out (revoke, queue nudges) needs no real channel layer."""
    with (
        mock.patch("navi_backend.devices.services.fleet.disconnect_device") as revoke,
        mock.patch(
            "navi_backend.orders.services.device_test_order_service."
            "notify_port_queue_changed"
        ),
    ):
        yield revoke


def machine_client(token):
    client = APIClient()
    client.credentials(HTTP_X_DEVICE_TOKEN=token)
    return client


class TestPermissions:
    @pytest.mark.parametrize(
        ("method", "name"),
        [
            ("get", "list"),
            ("post", "list"),
            ("get", "detail"),
            ("patch", "detail"),
            ("post", "rotate-token"),
            ("post", "test-order"),
            ("get", "events"),
        ],
    )
    def test_anonymous_401_and_non_staff_403(self, pi, method, name):
        url = LIST_URL if name == "list" else action_url(pi, name)

        anon = getattr(APIClient(), method)(url, {}, format="json")
        assert anon.status_code == 401

        client = APIClient()
        client.force_authenticate(UserFactory(is_staff=False))
        response = getattr(client, method)(url, {}, format="json")
        assert response.status_code == 403

    def test_device_token_is_not_staff_auth(self, pi):
        response = machine_client(pi.device_token).get(LIST_URL)
        assert response.status_code == 401

    def test_delete_not_allowed(self, admin_client, pi):
        assert admin_client.delete(detail_url(pi)).status_code == 405


class TestList:
    def test_shape(self, admin_client, pi, navi_port):
        response = admin_client.get(LIST_URL)

        assert response.status_code == 200
        assert set(response.data) == {"count", "next", "previous", "results"}
        device = response.data["results"][0]
        assert device["id"] == str(pi.id)
        assert device["enabled"] is True
        assert device["is_online"] is True
        assert device["navi_port"] == {"id": navi_port.id, "name": navi_port.name}
        machine = navi_port.espresso_machine
        assert device["espresso_machine"] == {
            "id": machine.id,
            "serial_number": machine.serial_number,
            "machine_type": machine.machine_type.name,
            "is_online": machine.is_online,
        }
        assert "device_token" not in device
        assert "token_hash" not in device

    def test_unattached_device_has_null_relations(self, admin_client, pi):
        device = admin_client.get(detail_url(pi)).data
        assert device["navi_port"] is None
        assert device["espresso_machine"] is None

    def test_filter_is_online(self, admin_client, pi):
        stale = RaspberryPiFactory(last_seen=timezone.now() - timedelta(minutes=5))
        never = RaspberryPiFactory(last_seen=None)

        online = admin_client.get(LIST_URL, {"is_online": "true"}).data["results"]
        offline = admin_client.get(LIST_URL, {"is_online": "false"}).data["results"]

        assert [d["id"] for d in online] == [str(pi.id)]
        assert {d["id"] for d in offline} == {str(stale.id), str(never.id)}

    def test_search(self, admin_client, pi):
        RaspberryPiFactory(name="Lobby Pi", location="HQ lobby")

        results = admin_client.get(LIST_URL, {"search": "lobby"}).data["results"]

        assert [d["name"] for d in results] == ["Lobby Pi"]


class TestCreate:
    def test_create_returns_token_once(self, admin_client, staff):
        port = NaviPortFactory(raspberry_pi=None)
        response = admin_client.post(
            LIST_URL,
            {
                "name": "Lobby Pi",
                "mac_address": "DC-A6-32-00-00-01",
                "location": "HQ lobby",
                "navi_port_id": str(port.id),
                "is_simulated": True,
            },
            format="json",
        )

        assert response.status_code == 201
        token = response.data["device_token"]
        pi = RaspberryPi.objects.get(pk=response.data["id"])
        assert pi.mac_address == "dc:a6:32:00:00:01"
        assert pi.slug == "lobby-pi"
        assert pi.is_connected is True
        assert pi.is_simulated is True
        assert pi.created_by == staff
        # Only the hash is stored, and the token authenticates the device.
        assert pi.token_hash == hash_device_token(token)
        assert token not in str(RaspberryPi.objects.filter(pk=pi.pk).values().get())
        assert response.data["navi_port"]["id"] == port.id
        assert machine_client(token).get(QUEUE_URL).status_code == 200

        # Never shown again.
        assert "device_token" not in admin_client.get(detail_url(pi)).data

    def test_rejects_bad_mac(self, admin_client):
        response = admin_client.post(
            LIST_URL, {"name": "x", "mac_address": "nope"}, format="json"
        )
        assert response.status_code == 400
        assert "mac_address" in response.data["error"]["message"]

    def test_rejects_unknown_port(self, admin_client):
        response = admin_client.post(
            LIST_URL,
            {
                "name": "x",
                "mac_address": "dc:a6:32:00:00:09",
                "navi_port_id": "00000000-0000-0000-0000-000000000000",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "navi_port_id" in response.data["error"]["message"]


class TestUpdate:
    def test_patch_fields(self, admin_client, pi):
        response = admin_client.patch(
            detail_url(pi), {"name": "Renamed", "location": "Back room"}, format="json"
        )

        assert response.status_code == 200
        assert response.data["name"] == "Renamed"
        assert response.data["location"] == "Back room"

    def test_disable_blocks_auth_and_revokes_socket(
        self,
        admin_client,
        pi,
        navi_port,
        mock_channel_layer,
        django_capture_on_commit_callbacks,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.patch(
                detail_url(pi), {"enabled": False}, format="json"
            )

        assert response.status_code == 200
        assert response.data["enabled"] is False
        assert machine_client(pi.device_token).get(QUEUE_URL).status_code == 401
        mock_channel_layer.assert_called_once_with(pi.pk)

    def test_attach_moves_port(self, admin_client, pi, navi_port):
        new_port = NaviPortFactory(raspberry_pi=RaspberryPiFactory())

        response = admin_client.patch(
            detail_url(pi), {"navi_port_id": str(new_port.id)}, format="json"
        )

        assert response.data["navi_port"]["id"] == new_port.id
        assert NaviPort.objects.get(pk=new_port.pk).raspberry_pi == pi
        # A Pi serves one port: the old one is released.
        assert NaviPort.objects.get(pk=navi_port.pk).raspberry_pi is None

    def test_detach_port(self, admin_client, pi, navi_port):
        response = admin_client.patch(
            detail_url(pi), {"navi_port_id": None}, format="json"
        )

        assert response.data["navi_port"] is None
        assert NaviPort.objects.get(pk=navi_port.pk).raspberry_pi is None


class TestRotateToken:
    def test_old_token_stops_working(  # noqa: PLR0913
        self,
        admin_client,
        staff,
        pi,
        navi_port,
        mock_channel_layer,
        django_capture_on_commit_callbacks,
    ):
        old_token = pi.device_token
        assert machine_client(old_token).get(QUEUE_URL).status_code == 200

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(action_url(pi, "rotate-token"))

        assert response.status_code == 200
        new_token = response.data["device_token"]
        assert new_token != old_token
        assert machine_client(old_token).get(QUEUE_URL).status_code == 401
        assert machine_client(new_token).get(QUEUE_URL).status_code == 200
        # Any open websocket on the old token is kicked.
        mock_channel_layer.assert_called_once_with(pi.pk)

        event = pi.events.get(type=DeviceEvent.Type.TOKEN_ROTATED)
        assert event.actor == staff


class TestTestOrder:
    def test_creates_zero_dollar_order_for_port(
        self, admin_client, staff, pi, navi_port
    ):
        menu_item = MenuItemFactory(status="A")

        response = admin_client.post(
            action_url(pi, "test-order"),
            {"menu_item_id": str(menu_item.id)},
            format="json",
        )

        assert response.status_code == 202
        order = Order.objects.get(pk=response.data["order_id"])
        assert read_qr_token(response.data["qr_token"]) == str(order.id)
        assert order.is_test is True
        assert order.payment is None
        assert order.user == staff
        assert order.navi_port == navi_port
        assert order.order_status == "O"
        assert order.price == 0
        assert order.items.get().menu_item == menu_item

        # The device sees it in its queue.
        queue = machine_client(pi.device_token).get(QUEUE_URL).data
        assert [o["id"] for o in queue] == [str(order.id)]
        assert queue[0]["is_test"] is True

        event = pi.events.get(type=DeviceEvent.Type.TEST_ORDER)
        assert event.payload["order_id"] == str(order.id)

    def test_defaults_to_an_active_menu_item(self, admin_client, pi, navi_port):
        MenuItemFactory(status="A")
        response = admin_client.post(action_url(pi, "test-order"), {}, format="json")
        assert response.status_code == 202
        assert Order.objects.get(pk=response.data["order_id"]).items.count() == 1

    def test_requires_navi_port(self, admin_client, pi):
        response = admin_client.post(action_url(pi, "test-order"), {}, format="json")
        assert response.status_code == 400
        assert "NaviPort" in response.data["error"]["message"]

    def test_requires_enabled_device(self, admin_client, navi_port):
        pi = navi_port.raspberry_pi
        pi.is_connected = False
        pi.save(update_fields=["is_connected"])
        response = admin_client.post(action_url(pi, "test-order"), {}, format="json")
        assert response.status_code == 400

    def test_unknown_menu_item(self, admin_client, pi, navi_port):
        response = admin_client.post(
            action_url(pi, "test-order"),
            {"menu_item_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        assert response.status_code == 400


class TestEvents:
    def test_newest_first_with_limit(self, admin_client, pi):
        for i in range(3):
            DeviceEvent.objects.create(
                raspberry_pi=pi, type=DeviceEvent.Type.CONNECTED, message=str(i)
            )
        DeviceEvent.objects.create(
            raspberry_pi=RaspberryPiFactory(), type=DeviceEvent.Type.CONNECTED
        )

        response = admin_client.get(action_url(pi, "events"), {"limit": 2})

        assert response.status_code == 200
        results = response.data["results"]
        assert [e["message"] for e in results] == ["2", "1"]
        assert set(results[0]) == {"id", "type", "message", "payload", "created_at"}
