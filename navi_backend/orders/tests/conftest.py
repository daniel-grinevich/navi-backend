import json

import pytest
from django.db import transaction
from rest_framework.test import APIRequestFactory

from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.menu.tests.factories import CustomizationFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.payments.tests.factories import PaymentFactory
from navi_backend.users.models import User
from navi_backend.users.tests.factories import UserFactory

from .factories import OrderCustomizationFactory
from .factories import OrderFactory
from .factories import OrderItemFactory


@pytest.fixture
def order(db):
    return OrderFactory(order_status="O")


@pytest.fixture
def order_data(db):
    user = UserFactory()
    navi_port = NaviPortFactory()
    payment = PaymentFactory()
    return json.dumps(
        {"user": user.pk, "navi_port": navi_port.pk, "payment": payment.pk}
    )


@pytest.fixture
def order_customization(db):
    return OrderCustomizationFactory()


@pytest.fixture
def order_item_and_customizations(db):
    order = OrderFactory(order_status="O")
    order_item = OrderItemFactory(order=order)
    order_item_2 = OrderItemFactory()
    order_customization_1 = OrderCustomizationFactory(order_item=order_item)
    order_customization_2 = OrderCustomizationFactory(order_item=order_item)
    order_customization_3 = OrderCustomizationFactory(order_item=order_item_2)
    return (
        order,
        order_item,
        order_customization_1,
        order_customization_2,
        order_customization_3,
    )


@pytest.fixture
def order_customization_data(db):
    user = UserFactory()
    order = OrderFactory(user=user)
    order_item = OrderItemFactory(order=order)
    customization = CustomizationFactory()
    return (
        order,
        order_item,
        json.dumps(
            {
                "order_item": order_item.pk,
                "customization": customization.pk,
                "quantity": 1,
            }
        ),
    )


@pytest.fixture
def order_item(db):
    return OrderItemFactory()


@pytest.fixture
def order_item_data(db):
    UserFactory()
    menu_item = MenuItemFactory()
    order = OrderFactory()
    return order, json.dumps(
        {
            "menu_item": menu_item.pk,
            "order": order.pk,
            "quantity": 1,
        }
    )


@pytest.fixture
def order_item_data2(db):
    UserFactory()
    menu_item = MenuItemFactory()
    order = OrderFactory()
    return order, json.dumps(
        {
            "menu_item": menu_item.pk,
            "order": order.pk,
            "quantity": 1,
        }
    )


@pytest.fixture
def order_and_order_items():
    order = OrderFactory(order_status="O")
    order2 = OrderFactory(order_status="O")
    order_item_1 = OrderItemFactory(order=order)
    order_item_2 = OrderItemFactory(order=order)
    order_item_3 = OrderItemFactory(order=order2)
    return order, order_item_1, order_item_2, order_item_3


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="admin@email.com",
        password="adminpass",  # noqa: S106
    )


@pytest.fixture
def user_and_orders():
    user = UserFactory()
    own_order = OrderFactory(user=user, order_status="O")
    other_order = OrderFactory(order_status="O")  # Another user's order
    return user, own_order, other_order


@pytest.fixture
def admin_and_orders(admin_user):
    admin = admin_user
    orders = OrderFactory.create_batch(5, order_status="O")  # Create 5 random orders
    return admin, orders


@pytest.fixture
def api_rf() -> APIRequestFactory:
    return APIRequestFactory()


@pytest.fixture
def get_response(api_rf):
    """Helper to get response from a viewset."""

    def _get_response(user, view, **kwargs):
        method = kwargs.pop("method")
        url = kwargs.pop("url")
        pk = kwargs.pop("pk", None)
        data = kwargs.pop("data", None)
        content_type = kwargs.pop("content_type", "application/json")

        with transaction.atomic():
            request = api_rf.generic(method, url, data=data, content_type=content_type)
            request.user = user
            if pk is not None:
                return view(request, pk=pk)
            return view(request)

    return _get_response


@pytest.fixture
def order_nested_data(db):
    menu_item = MenuItemFactory()
    navi_port = NaviPortFactory()
    customization = CustomizationFactory()
    return json.dumps(
        {
            "navi_port": navi_port.pk,
            "items": [
                {
                    "menu_item": menu_item.pk,
                    "quantity": 2,
                    "unit_price": "5.00",
                    "customizations": [
                        {
                            "customization": customization.pk,
                            "quantity": 1,
                            "unit_price": "2.00",
                        }
                    ],
                }
            ],
        }
    )
