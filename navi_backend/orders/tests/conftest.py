import pytest
from .factories import OrderItemFactory, OrderFactory, MenuItemFactory
from navi_backend.users.models import User


@pytest.fixture
def new_order(db):
    return OrderFactory()


@pytest.fixture
def new_order_item(db):
    return OrderItemFactory()


@pytest.fixture
def new_menu_item(db):
    return MenuItemFactory()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(email="admin@email.com", password="adminpass")
