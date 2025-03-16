import pytest
import json
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from .factories import (
    OrderItemFactory,
    OrderFactory,
    MenuItemFactory,
    PaymentTypeFactory,
    NaviPortFactory,
    IngredientFactory,
    CategoryFactory,
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
    return {
        "user": user.slug,
        "payment_type": payment_type.slug,
        "navi_port": navi_port.pk,
        "total_price": 7.00,
    }


@pytest.fixture
def order_item(db):
    return OrderItemFactory()


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
