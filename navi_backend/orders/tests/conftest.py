import pytest
import json
from django.utils import timezone, dateformat
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from .factories import (
    OrderItemFactory,
    OrderFactory,
    MenuItemFactory,
    PaymentTypeFactory,
    NaviPortFactory,
    IngredientFactory,
    CategoryFactory,
    MenuItemIngredientFactory,
    EspressoMachineFactory,
    MachineTypeFactory,
    RasberryPiFactory,
)
from navi_backend.users.tests.factories import UserFactory
from rest_framework.test import APIRequestFactory
from navi_backend.users.models import User


@pytest.fixture
def order(db):
    return OrderFactory()


@pytest.fixture
def order_data(db):
    user = UserFactory()
    payment_type = PaymentTypeFactory()
    navi_port = NaviPortFactory()
    datetime = dateformat.format(timezone.now(), "Y-m-d H:i:s")
    return json.dumps(
        {
            "user": user.pk,
            "payment_type": payment_type.pk,
            "navi_port": navi_port.pk,
            "price": 7.00,
            "created_at": datetime,
            "created_by": user.pk,
            "updated_at": datetime,
            "updated_by": user.pk,
            "slug": "test1",
        }
    )


@pytest.fixture
def order_item(db):
    return OrderItemFactory()


@pytest.fixture
def order_item_data(db):
    user = UserFactory()
    menu_item = MenuItemFactory()
    order = OrderFactory()
    datetime = dateformat.format(timezone.now(), "Y-m-d H:i:s")
    return json.dumps(
        {
            "menu_item": menu_item.pk,
            "order": order.pk,
            "navi_port": navi_port.pk,
            "quantity": 1,
            "unit_price": 7.00,
            "created_at": datetime,
            "created_by": user.pk,
            "updated_at": datetime,
            "updated_by": user.pk,
            "slug": "test1",
        }
    )


@pytest.fixture
def order_and_order_items():
    order = OrderFactory()
    order_item_1 = OrderItemFactory(order=order)
    order_item_2 = OrderItemFactory(order=order)
    return order, order_item_1, order_item_2


@pytest.fixture
def menu_item(db):
    return MenuItemFactory(name="Latte")


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
def ingredient_data(admin_user):
    time = timezone.now
    return json.dumps(
        {
            "slug": "test1",
            "name": "Tomato Sauce",
            "description": "Test",
            "is_allergen": "False",
            "status": "A",
            "created_at": "2012-04-23T18:25:43.511Z",
            "updated_at": "2012-04-23T18:25:43.511Z",
            "created_by": admin_user.pk,
            "updated_by": admin_user.pk,
        }
    )


@pytest.fixture
def menu_item_data(admin_user):
    category = CategoryFactory()
    image_file = SimpleUploadedFile(
        "Latte.png",
        content=open("navi_backend/media/product_images/Latte.png", "rb").read(),
        content_type="image/png",
    )

    return {
        "slug": "test1",
        "name": "Over-Priced Latte",
        "description": "Over-Priced Latte",
        "body": "Over-Priced Latte",
        "price": "12.99",
        "category": category.pk,
        "image": image_file,
        "status": "A",
        "created_at": "2012-04-23T18:25:43.511Z",
        "updated_at": "2012-04-23T18:25:43.511Z",
        "created_by": admin_user.pk,
        "updated_by": admin_user.pk,
    }


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

    def _get_response(
        user, view, method, url, data=None, pk=None, content_type="application/json"
    ):
        with transaction.atomic():
            request = api_rf.generic(method, url, data=data, content_type=content_type)
            request.user = user
            if pk:
                return view(request, pk=pk)
            return view(request)

    return _get_response


@pytest.fixture
def ingredient():
    ingredient = IngredientFactory(name="Espresso")
    return ingredient


@pytest.fixture
def menu_item_ingredient():
    menu_item = MenuItemFactory(name="Latte")
    ingredient = IngredientFactory(name="Milk")
    return MenuItemIngredientFactory(
        menu_item=menu_item, ingredient=ingredient, quantity="200", unit="g"
    )


@pytest.fixture
def menu_item_ingredient_data():
    menu_item = MenuItemFactory(name="Capp")
    ingredient = IngredientFactory(name="espresso")
    return json.dumps(
        {
            "menu_item": menu_item.pk,
            "ingredient": ingredient.pk,
            "quantity": "200",
            "unit": "g",
        }
    )


@pytest.fixture
def navi_port_data(admin_user):
    espresso_machine = EspressoMachineFactory(name="navi1")
    rasberry_pi = RasberryPiFactory(name="razz")
    return json.dumps(
        {
            "slug": "test1",
            "name": "Navi_Port_1",
            "status": "A",
            "created_at": "2012-04-23T18:25:43.511Z",
            "updated_at": "2012-04-23T18:25:43.511Z",
            "created_by": admin_user.pk,
            "updated_by": admin_user.pk,
            "rasberry_pi": rasberry_pi.pk,
            "espresso_machine": espresso_machine.pk,
        }
    )


@pytest.fixture
def navi_port():
    return NaviPortFactory(name="Navi_Port_2")


@pytest.fixture
def payment_type_data(admin_user):
    return json.dumps(
        {
            "slug": "test1",
            "name": "Payment_Type_1",
            "status": "A",
            "created_at": "2012-04-23T18:25:43.511Z",
            "updated_at": "2012-04-23T18:25:43.511Z",
            "created_by": admin_user.pk,
            "updated_by": admin_user.pk,
        }
    )


@pytest.fixture
def payment_type():
    return PaymentTypeFactory(name="Payment_2")
