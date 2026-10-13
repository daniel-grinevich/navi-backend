"""Customers can't rewrite order status/routing or order archived items.

Audit S2 (order_status/navi_port read-only for non-staff, PUT staff-only),
S12 (archived menu items rejected) and S10 (order websocket id handling).
"""

import pytest
from rest_framework.test import APIClient

from config.routing import websocket_urlpatterns
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.menu.models import MenuItem
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.api.serializers import OrderItemSerializer
from navi_backend.orders.consumers import _get_order_for_user
from navi_backend.users.tests.factories import UserFactory

from .factories import OrderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def order(owner):
    return OrderFactory(user=owner, order_status="O")


def _detail(order):
    return f"/api/orders/{order.pk}/"


class TestCustomerOrderUpdates:
    @pytest.mark.parametrize("new_status", ["D", "S", "C"])
    def test_owner_cannot_patch_status(self, api_client, owner, order, new_status):
        api_client.force_authenticate(user=owner)

        resp = api_client.patch(
            _detail(order), {"order_status": new_status}, format="json"
        )

        assert resp.status_code == 400
        order.refresh_from_db()
        assert order.order_status == "O"

    def test_owner_cannot_reopen_done_order(self, api_client, owner):
        # D -> O would re-mint a valid QR for a finished (already charged) order.
        order = OrderFactory(user=owner, order_status="D")
        api_client.force_authenticate(user=owner)

        resp = api_client.patch(_detail(order), {"order_status": "O"}, format="json")

        assert resp.status_code in (400, 403)
        order.refresh_from_db()
        assert order.order_status == "D"

    def test_owner_cannot_reroute(self, api_client, owner, order):
        original_port = order.navi_port
        api_client.force_authenticate(user=owner)

        resp = api_client.patch(
            _detail(order), {"navi_port": str(NaviPortFactory().pk)}, format="json"
        )

        assert resp.status_code == 400
        order.refresh_from_db()
        assert order.navi_port == original_port

    def test_owner_cannot_put(self, api_client, owner, order):
        api_client.force_authenticate(user=owner)

        resp = api_client.put(
            _detail(order),
            {"order_status": "D", "navi_port": str(order.navi_port.pk)},
            format="json",
        )

        assert resp.status_code == 403
        order.refresh_from_db()
        assert order.order_status == "O"

    def test_other_user_cannot_patch(self, api_client, order):
        api_client.force_authenticate(user=UserFactory())

        resp = api_client.patch(_detail(order), {"order_status": "C"}, format="json")

        assert resp.status_code in (403, 404)
        order.refresh_from_db()
        assert order.order_status == "O"

    def test_owner_can_still_cancel_unclaimed_order(self, api_client, owner, order):
        api_client.force_authenticate(user=owner)

        resp = api_client.put(f"/api/orders/{order.pk}/cancel_order/")

        assert resp.status_code == 200
        order.refresh_from_db()
        assert order.order_status == "C"

    def test_owner_cannot_cancel_sent_order(self, api_client, owner):
        order = OrderFactory(user=owner, order_status="S")
        api_client.force_authenticate(user=owner)

        resp = api_client.put(f"/api/orders/{order.pk}/cancel_order/")

        assert resp.status_code == 400
        order.refresh_from_db()
        assert order.order_status == "S"


class TestStaffOrderUpdates:
    def test_staff_can_patch_status(self, api_client, admin_user, order):
        api_client.force_authenticate(user=admin_user)

        resp = api_client.patch(_detail(order), {"order_status": "D"}, format="json")

        assert resp.status_code == 200
        order.refresh_from_db()
        assert order.order_status == "D"

    def test_staff_can_reroute(self, api_client, admin_user, order):
        new_port = NaviPortFactory()
        api_client.force_authenticate(user=admin_user)

        resp = api_client.patch(
            _detail(order), {"navi_port": str(new_port.pk)}, format="json"
        )

        assert resp.status_code == 200
        order.refresh_from_db()
        assert order.navi_port == new_port

    def test_staff_dispatch_of_done_order_is_400(self, api_client, admin_user):
        order = OrderFactory(order_status="D")
        api_client.force_authenticate(user=admin_user)

        resp = api_client.post(
            f"/api/orders/{order.pk}/dispatch/",
            {"naviportId": str(order.navi_port.pk)},
            format="json",
        )

        assert resp.status_code == 400
        order.refresh_from_db()
        assert order.order_status == "D"


class TestOrderItemMenuItem:
    def _serializer(self, order, menu_item):
        return OrderItemSerializer(
            data={"menu_item": str(menu_item.pk), "order": str(order.pk), "quantity": 1}
        )

    def test_active_item_accepted(self, order):
        serializer = self._serializer(order, MenuItemFactory(status="A"))
        assert serializer.is_valid(), serializer.errors

    @pytest.mark.parametrize("status", ["R", "I", "D"])
    def test_non_active_item_rejected(self, order, status):
        serializer = self._serializer(order, MenuItemFactory(status=status))
        assert not serializer.is_valid()
        assert "menu_item" in serializer.errors

    def test_deleted_item_rejected(self, order):
        item = MenuItemFactory(status="A")
        MenuItem.objects.with_deleted().filter(pk=item.pk).update(is_deleted=True)
        serializer = self._serializer(order, item)
        assert not serializer.is_valid()
        assert "menu_item" in serializer.errors


class TestOrderWebsocketIds:
    def test_route_requires_uuid(self, order):
        pattern = websocket_urlpatterns[0].pattern
        assert pattern.match("ws/orders/not-a-uuid/") is None
        assert pattern.match(f"ws/orders/{order.pk}/") is not None

    def test_lookup_with_malformed_id_returns_none(self, owner):
        assert _get_order_for_user.func("not-a-uuid", owner) is None
