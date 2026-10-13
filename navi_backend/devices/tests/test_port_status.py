"""NaviPort sticker deep link + staff maintenance toggle."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.devices.services.port_status import get_port_status_by_slug
from navi_backend.devices.tests.factories import EspressoMachineFactory
from navi_backend.devices.tests.factories import MachineTypeFactory
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

CONTRACT_KEYS = {
    "id",
    "slug",
    "name",
    "address",
    "is_online",
    "accepting_orders",
    "status_message",
    "queue_length",
    "est_wait_seconds",
    "menu_item_ids",
}


def by_slug_url(slug):
    return reverse("api:navi-port-by-slug", kwargs={"slug": slug})


def admin_url(port):
    return reverse("api:admin-navi-port", kwargs={"pk": port.pk})


def cached_status():
    status = get_port_status_by_slug("hq-lobby")
    assert status is not None
    return status


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def unrestricted_machine():
    return EspressoMachineFactory(machine_type=MachineTypeFactory())


@pytest.fixture
def port(unrestricted_machine):
    return NaviPortFactory(
        name="HQ Lobby",
        slug="hq-lobby",
        address_line_1="1 Main St",
        city="Boston",
        state_or_region="MA",
        postal_code="02110",
        espresso_machine=unrestricted_machine,
        raspberry_pi=RaspberryPiFactory(last_seen=timezone.now()),
    )


class TestBySlug:
    def test_public_contract(self, api_client, port):
        resp = api_client.get(by_slug_url("hq-lobby"))

        assert resp.status_code == 200
        assert set(resp.data) == CONTRACT_KEYS
        assert resp.data["id"] == str(port.id)
        assert resp.data["slug"] == "hq-lobby"
        assert resp.data["name"] == "HQ Lobby"
        assert resp.data["address"] == {
            "line1": "1 Main St",
            "city": "Boston",
            "state": "MA",
            "postal_code": "02110",
        }
        assert resp.data["is_online"] is True
        assert resp.data["accepting_orders"] is True
        assert resp.data["status_message"] is None
        assert resp.data["queue_length"] == 0
        assert resp.data["est_wait_seconds"] == 0
        assert resp.data["menu_item_ids"] is None

    def test_unknown_slug_is_404_envelope(self, api_client):
        resp = api_client.get(by_slug_url("nope"))

        assert resp.status_code == 404
        assert resp.data["error"]["code"] == 404
        assert resp.data["error"]["message"]

    def test_ignores_bad_auth_cookie(self, api_client, port):
        api_client.cookies["access_token"] = "garbage"
        assert api_client.get(by_slug_url("hq-lobby")).status_code == 200

    def test_queue_length_and_wait(self, api_client, port, settings):
        settings.NAVI_PORT_SECONDS_PER_DRINK = 90
        OrderFactory(navi_port=port, order_status="O")
        OrderFactory(navi_port=port, order_status="O")
        OrderFactory(navi_port=port, order_status="S")
        # Not queued: finished, cancelled, or at another port.
        OrderFactory(navi_port=port, order_status="D")
        OrderFactory(navi_port=port, order_status="C")
        OrderFactory(order_status="O")

        resp = api_client.get(by_slug_url("hq-lobby"))

        assert resp.data["queue_length"] == 3
        assert resp.data["est_wait_seconds"] == 270

    def test_wait_uses_setting(self, api_client, port, settings):
        settings.NAVI_PORT_SECONDS_PER_DRINK = 45
        OrderFactory.create_batch(2, navi_port=port, order_status="O")

        assert api_client.get(by_slug_url("hq-lobby")).data["est_wait_seconds"] == 90

    def test_offline_pi(self, api_client, port):
        port.raspberry_pi.last_seen = timezone.now() - timedelta(minutes=5)
        port.raspberry_pi.save()

        resp = api_client.get(by_slug_url("hq-lobby"))

        assert resp.data["is_online"] is False
        assert resp.data["accepting_orders"] is False

    def test_no_pi_is_offline(self, api_client, port):
        port.raspberry_pi = None
        port.save()

        resp = api_client.get(by_slug_url("hq-lobby"))

        assert resp.data["is_online"] is False
        assert resp.data["accepting_orders"] is False

    def test_paused_shows_status_message(self, api_client, port):
        port.accepting_orders = False
        port.status_message = "Out of milk - back at 2pm"
        port.save()

        resp = api_client.get(by_slug_url("hq-lobby"))

        assert resp.data["is_online"] is True
        assert resp.data["accepting_orders"] is False
        assert resp.data["status_message"] == "Out of milk - back at 2pm"

    def test_status_message_hidden_while_accepting(self, api_client, port):
        port.status_message = "leftover note"
        port.save()

        assert api_client.get(by_slug_url("hq-lobby")).data["status_message"] is None

    def test_menu_item_ids_from_supported_drinks(self, api_client, port):
        latte = MenuItemFactory(name="Latte", slug="latte", status="A")
        mocha = MenuItemFactory(name="Mocha", slug="mocha", status="A")
        inactive = MenuItemFactory(name="Chai", slug="chai", status="I")
        MenuItemFactory(name="Tea", slug="tea", status="A")  # not supported
        port.espresso_machine.machine_type.supported_drinks.add(latte, mocha, inactive)

        resp = api_client.get(by_slug_url("hq-lobby"))

        assert set(resp.data["menu_item_ids"]) == {str(latte.id), str(mocha.id)}

    def test_no_machine_is_unrestricted(self, api_client, port):
        port.espresso_machine = None
        port.save()

        assert api_client.get(by_slug_url("hq-lobby")).data["menu_item_ids"] is None


class TestCaching:
    @pytest.fixture(autouse=True)
    def locmem_cache(self, settings):
        settings.CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "port-status-tests",
            }
        }
        cache.clear()
        yield
        cache.clear()

    def test_cached_between_requests(self, port, django_assert_num_queries):
        get_port_status_by_slug("hq-lobby")
        with django_assert_num_queries(0):
            get_port_status_by_slug("hq-lobby")

    def test_port_save_invalidates(self, port):
        assert cached_status()["accepting_orders"] is True

        port.accepting_orders = False
        port.save()

        assert cached_status()["accepting_orders"] is False

    def test_supported_drinks_change_invalidates(self, port):
        assert cached_status()["menu_item_ids"] is None

        latte = MenuItemFactory(name="Latte", slug="latte", status="A")
        port.espresso_machine.machine_type.supported_drinks.add(latte)

        assert cached_status()["menu_item_ids"] == [str(latte.id)]

    def test_admin_patch_invalidates(self, api_client, port):
        assert cached_status()["accepting_orders"] is True
        api_client.force_authenticate(UserFactory(is_staff=True))

        api_client.patch(admin_url(port), {"accepting_orders": False}, format="json")

        assert cached_status()["accepting_orders"] is False


class TestAdminPatch:
    @pytest.fixture
    def staff_client(self, api_client):
        api_client.force_authenticate(UserFactory(is_staff=True))
        return api_client

    def test_pause_with_message(self, staff_client, port):
        resp = staff_client.patch(
            admin_url(port),
            {"accepting_orders": False, "status_message": "Descaling"},
            format="json",
        )

        assert resp.status_code == 200
        assert set(resp.data) == CONTRACT_KEYS
        assert resp.data["accepting_orders"] is False
        assert resp.data["status_message"] == "Descaling"
        port.refresh_from_db()
        assert port.accepting_orders is False
        assert port.status_message == "Descaling"

    def test_null_message_clears(self, staff_client, port):
        port.status_message = "Descaling"
        port.save()

        resp = staff_client.patch(
            admin_url(port), {"status_message": None}, format="json"
        )

        assert resp.status_code == 200
        port.refresh_from_db()
        assert port.status_message == ""

    def test_resume(self, staff_client, port):
        port.accepting_orders = False
        port.save()

        resp = staff_client.patch(
            admin_url(port), {"accepting_orders": True}, format="json"
        )

        assert resp.data["accepting_orders"] is True

    def test_non_staff_forbidden(self, api_client, port):
        api_client.force_authenticate(UserFactory())

        resp = api_client.patch(
            admin_url(port), {"accepting_orders": False}, format="json"
        )

        assert resp.status_code == 403
        port.refresh_from_db()
        assert port.accepting_orders is True

    def test_anonymous_rejected(self, api_client, port):
        resp = api_client.patch(
            admin_url(port), {"accepting_orders": False}, format="json"
        )

        assert resp.status_code in (401, 403)

    def test_unknown_port_404(self, staff_client, port):
        port_id = port.pk
        port.delete()

        resp = staff_client.patch(
            reverse("api:admin-navi-port", kwargs={"pk": port_id}),
            {"accepting_orders": False},
            format="json",
        )

        assert resp.status_code == 404
