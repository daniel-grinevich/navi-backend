import pytest

from navi_backend.users.models import User
from navi_backend.users.tests.factories import UserFactory

from .factories import OrderFactory


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="admin@email.com",
        password="adminpass",
    )


@pytest.fixture
def user_and_orders():
    user = UserFactory()
    own_order = OrderFactory(user=user, order_status="O")
    other_order = OrderFactory(order_status="O")  # Another user's order
    return user, own_order, other_order
