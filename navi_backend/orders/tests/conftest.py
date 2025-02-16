import pytest
from .factories import OrderItemFactory, OrderFactory, MenuItemFactory


@pytest.fixture
def new_order(db):
    return OrderFactory()


@pytest.fixture
def new_order_item(db):
    return OrderItemFactory()
