"""API tests for order list scoping (client vs admin) and pagination."""

import pytest
from rest_framework.test import APIClient

from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.users.tests.factories import UserFactory

PAGE_KEYS = {"count", "next", "previous", "results"}


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestClientOrderList:
    """GET /api/orders/ is always the caller's own orders, even for staff."""

    def test_regular_user_sees_only_own_orders(self, api_client, user_and_orders):
        user, own_order, other_order = user_and_orders
        api_client.force_authenticate(user=user)

        resp = api_client.get("/api/orders/")

        assert resp.status_code == 200
        ids = {str(o["id"]) for o in resp.data["results"]}
        assert str(own_order.id) in ids
        assert str(other_order.id) not in ids

    def test_admin_sees_only_own_orders_on_client_list(self, api_client, admin_user):
        # Admin has no orders of their own; other users' orders must not leak
        # onto the client portal list even though the admin is staff.
        OrderFactory.create_batch(3, order_status="O")
        api_client.force_authenticate(user=admin_user)

        resp = api_client.get("/api/orders/")

        assert resp.status_code == 200
        assert resp.data["count"] == 0

    def test_response_is_paginated(self, api_client, user_and_orders):
        user, _, _ = user_and_orders
        api_client.force_authenticate(user=user)

        resp = api_client.get("/api/orders/")

        assert PAGE_KEYS.issubset(resp.data.keys())

    def test_status_filter(self, api_client):
        user = UserFactory()
        OrderFactory(user=user, order_status="O")
        OrderFactory(user=user, order_status="D")
        api_client.force_authenticate(user=user)

        resp = api_client.get("/api/orders/", {"status": "D"})

        statuses = {o["order_status"] for o in resp.data["results"]}
        assert statuses == {"D"}

    def test_serializes_created_at(self, api_client, user_and_orders):
        user, _, _ = user_and_orders
        api_client.force_authenticate(user=user)

        resp = api_client.get("/api/orders/")

        assert resp.data["results"]
        assert "created_at" in resp.data["results"][0]


@pytest.mark.django_db
class TestAdminOrderList:
    """GET /api/admin/orders/ is staff-only and returns every user's orders."""

    def test_admin_sees_all_orders(self, api_client, admin_user):
        # Orders belonging to several different users, none of them the admin.
        OrderFactory(order_status="O")
        OrderFactory(order_status="O")
        OrderFactory(order_status="O")
        api_client.force_authenticate(user=admin_user)

        resp = api_client.get("/api/admin/orders/")

        assert resp.status_code == 200
        assert resp.data["count"] == 3

    def test_regular_user_forbidden(self, api_client):
        api_client.force_authenticate(user=UserFactory())

        resp = api_client.get("/api/admin/orders/")

        assert resp.status_code == 403

    def test_status_filter(self, api_client, admin_user):
        OrderFactory(order_status="O")
        OrderFactory(order_status="C")
        api_client.force_authenticate(user=admin_user)

        resp = api_client.get("/api/admin/orders/", {"status": "C"})

        statuses = {o["order_status"] for o in resp.data["results"]}
        assert statuses == {"C"}
