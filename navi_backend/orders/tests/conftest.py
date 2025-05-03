import pytest
import json
from django.utils import timezone, dateformat
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from .factories import (
    OrderItemFactory,
    OrderFactory,
    MenuItemFactory,
    NaviPortFactory,
    IngredientFactory,
    CategoryFactory,
    MenuItemIngredientFactory,
    EspressoMachineFactory,
    MachineTypeFactory,
    RasberryPiFactory,
    CustomizationFactory,
    CustomizationGroupFactory,
    OrderCustomizationFactory,
)
from navi_backend.users.tests.factories import UserFactory
from navi_backend.payments.tests.factories import PaymentFactory
from rest_framework.test import APIRequestFactory
from navi_backend.users.models import User


@pytest.fixture
def order(db):
    return OrderFactory(status="O")


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
    order = OrderFactory(status="O")
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
    user = UserFactory()
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
    user = UserFactory()
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
    order = OrderFactory(status="O")
    order2 = OrderFactory(status="O")
    order_item_1 = OrderItemFactory(order=order)
    order_item_2 = OrderItemFactory(order=order)
    order_item_3 = OrderItemFactory(order=order2)
    return order, order_item_1, order_item_2, order_item_3


@pytest.fixture
def menu_item(db):
    return MenuItemFactory(name="Latte")


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(email="admin@email.com", password="adminpass")


@pytest.fixture
def user_and_orders():
    user = UserFactory()
    own_order = OrderFactory(user=user, status="O")
    other_order = OrderFactory(status="O")  # Another user's order
    return user, own_order, other_order


@pytest.fixture
def ingredient_data(admin_user):
    return json.dumps(
        {
            "name": "Tomato Sauce",
            "description": "Test",
            "is_allergen": "False",
            "status": "A",
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
        "name": "Over-Priced Latte",
        "description": "Over-Priced Latte",
        "body": "Over-Priced Latte",
        "price": "12.99",
        "category": category.pk,
        "image": image_file,
        "status": "A",
    }


@pytest.fixture
def admin_and_orders(admin_user):
    admin = admin_user
    orders = OrderFactory.create_batch(5, status="O")  # Create 5 random orders
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
            "name": "Navi_Port_1",
            "status": "A",
            "rasberry_pi": rasberry_pi.pk,
            "espresso_machine": espresso_machine.pk,
        }
    )


@pytest.fixture
def navi_port():
    return NaviPortFactory(name="Navi_Port_2")


@pytest.fixture
def rasberry_pi(db):
    return RasberryPiFactory()


@pytest.fixture
def rasberry_pi_data(admin_user):
    return json.dumps(
        {
            "name": "Rasberry_Pi_1",
            "mac_address": "01:23:45:67:89:AB",
            "ip_address": "192.168.1.1",
            "location": "test",
            "is_connected": True,
            "firmware_version": "v1",
        }
    )


@pytest.fixture
def espresso_machine(db):
    return EspressoMachineFactory()


@pytest.fixture
def espresso_machine_data(admin_user):
    machine_type = MachineTypeFactory()
    return json.dumps(
        {
            "name": "Espresso_Machine_1",
            "machine_type": machine_type.pk,
            "serial_number": "12345",
            "ip_address": "192.168.1.1",
            "port": 1,
            "is_online": True,
            "last_maintenance_at": "2012-04-23T18:25:43.511Z",
        }
    )


@pytest.fixture
def machine_type(db):
    return MachineTypeFactory()


@pytest.fixture
def machine_type_data(admin_user):
    menu_item = MenuItemFactory()

    return json.dumps(
        {
            "name": "Machine_Type_1",
            "model_number": "1",
            "maintenance_frequency": 30,
            "supported_drinks": [menu_item.pk],
        }
    )


@pytest.fixture
def customization(db):
    return CustomizationFactory()


@pytest.fixture
def customization_data(admin_user):
    group = CustomizationGroupFactory()
    return json.dumps(
        {
            "name": "Customization_1",
            "description": "Test",
            "price": 10.00,
            "display_order": 1,
            "group": group.pk,
        }
    )


@pytest.fixture
def customization_group(db):
    return CustomizationGroupFactory()


@pytest.fixture
def customization_group_data(admin_user):
    category = CategoryFactory()
    return json.dumps(
        {
            "name": "Customization_Group_1",
            "description": "Test",
            "category": category.pk,
            "display_order": 1,
            "is_required": True,
        }
    )


@pytest.fixture
def category(db):
    return CategoryFactory()


@pytest.fixture
def category_data(admin_user):
    return json.dumps(
        {
            "name": "Category_1",
        }
    )


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
