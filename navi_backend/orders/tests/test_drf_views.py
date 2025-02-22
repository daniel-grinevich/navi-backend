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
from .conftest import new_order, new_order_item, new_menu_item, admin_user
from navi_backend.users.models import User
from navi_backend.orders.api.views import (
    MenuItemViewSet,
    OrderItemViewSet,
    OrderViewSet,
)


class TestOrderViewSet:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_get_queryset(self, admin_user, api_rf: APIRequestFactory):
        view = OrderViewSet.as_view({"get": "list"})
        request = api_rf.get("/api/orders/")
        request.user = admin_user

        response = view(request)

        assert response.status_code == status.HTTP_200_OK

    # Add test to make sure Admin can see all orders and normal users can only see their orders
