import pytest
from django.utils import timezone
from .factories import (
    OrderItemFactory,
    OrderFactory,
    MenuItemFactory,
    PaymentTypeFactory,
    PortFactory,
)
from navi_backend.users.tests.factories import UserFactory
from rest_framework.test import APIRequestFactory
from navi_backend.users.models import User


@pytest.fixture
def new_order(db):
    return OrderFactory()


@pytest.fixture
def order_data(db):
    user = UserFactory()
    payment_type = PaymentTypeFactory()
    port = PortFactory()
    return {
        "user": user.pk,
        "payment_type": payment_type.pk,
        "port": port.pk,
        "total_price": 7.00,
    }


@pytest.fixture
def new_order_item(db):
    return OrderItemFactory()


@pytest.fixture
def new_menu_item(db):
    return MenuItemFactory()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(email="admin@email.com", password="adminpass")


@pytest.fixture
def user_and_orders():
    user = UserFactory()
    own_order = OrderFactory(user=user)
    other_order = OrderFactory()  # Another user's order
    return user, own_order, other_order


@pytest.fixture
def admin_and_orders(admin_user):
    admin = admin_user
    orders = OrderFactory.create_batch(5)  # Create 5 random orders
    return admin, orders


@pytest.fixture
def api_rf() -> APIRequestFactory:
    return APIRequestFactory()


@pytest.fixture
def get_response(api_rf: APIRequestFactory):
    """Helper to get response from a viewset."""

    def _get_response(user, view, method, url, data=None, pk=None):
        request = api_rf.generic(method, url, data=data, format="json")
        request.user = user
        if pk:
            return view(request, pk=pk)
        return view(request)

    return _get_response
