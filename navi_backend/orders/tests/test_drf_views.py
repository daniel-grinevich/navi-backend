import pytest
from rest_framework.test import APIRequestFactory
from rest_framework import status
from navi_backend.orders.models import (
    Order,
    OrderItem,
    Category,
    PaymentType,
    Port,
    MenuItem,
)
from .factories import OrderFactory
from navi_backend.orders.tests.factories import UserFactory
from navi_backend.users.models import User
from navi_backend.orders.api.views import (
    MenuItemViewSet,
    OrderItemViewSet,
    OrderViewSet,
)

# Potentially switch request setup to generic function


@pytest.mark.django_db
class TestOrderViewSet:

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/orders/"),
            ("retrieve", "GET", "/orders/{pk}/"),
        ],
    )
    def test_not_admin_access(
        self, user_and_orders, get_response, view_name, method, url
    ):
        """Non-admin users should only see their own orders."""
        user, own_order, other_order = user_and_orders
        view = OrderViewSet.as_view({method.lower(): view_name})

        # List View
        if view_name == "list":
            response = get_response(user, view, method, url)
            order_ids = [order["slug"] for order in response.data]
            assert str(own_order.slug) in order_ids
            assert str(other_order.slug) not in order_ids

        # Retrieve View
        if view_name == "retrieve":
            response = get_response(
                user, view, method, url.format(pk=own_order.pk), pk=own_order.pk
            )
            assert response.status_code == status.HTTP_200_OK

            response = get_response(
                user, view, method, url.format(pk=other_order.pk), pk=other_order.pk
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/orders/"),
            ("retrieve", "GET", "/orders/{pk}/"),
        ],
    )
    def test_admin_access(self, admin_and_orders, get_response, view_name, method, url):
        """Admin users should have access to all orders."""
        admin, orders = admin_and_orders
        view = OrderViewSet.as_view({method.lower(): view_name})

        # List View
        if view_name == "list":
            response = get_response(admin, view, method, url)
            order_ids = [order["slug"] for order in response.data]
            assert len(order_ids) == len(orders)
            assert all(str(order.slug) in order_ids for order in orders)

        # Retrieve View
        if view_name == "retrieve":
            for order in orders:
                response = get_response(
                    admin, view, method, url.format(pk=order.pk), pk=order.pk
                )
                assert response.status_code == status.HTTP_200_OK
