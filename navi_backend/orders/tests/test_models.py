import pytest
from django.test import TestCase
from .factories import OrderFactory, OrderItemFactory
from ..models import Order
import random
from django.contrib.auth import get_user_model

User = get_user_model()


def test_create_order(new_order):
    assert new_order


def test_create_order_item(new_order_item):
    assert new_order_item


""" @pytest.mark.parametrize(
    "menu_item_attrs",
    [
        {
            "name": "Pizza",
            "description": "A tasty pie with tomato sauce.",
            "price": 12.99,
            "menu_name": "Dinner",
        },
        {
            "name": "Burger",
            "description": "Smash burger with caramelized onions.",
            "price": 10.50,
            "menu_name": "Lunch",
        },
        # Add more menu items with associated menu names
    ],
)
def test_create_order_workflow(
    db,
    order_item_factory,
    menu_item_factory,
    menu_factory,
    menu_item_attrs,
    order_factory,
):
    menu = menu_factory.create(name=menu_item_attrs["menu_name"])

    menu_item = menu_item_factory.create(
        name=menu_item_attrs["name"],
        description=menu_item_attrs["description"],
        price=menu_item_attrs["price"],
    )

    menu.item = menu_item

    assert menu.item.name == menu_item.name
    assert menu.item == menu_item
    order = order_factory.create()

    order_item = order_item_factory.create(order=order, item=menu_item, quantity=1)

    assert order_item.item.price * order_item.quantity == menu_item.price


class OrderTest(TestCase):
    def setUp(self):
        self.order = OrderFactory(
            customer="Daniel Grinevich", total=32.00, tip=5.00, status="placed"
        )
        self.menu_items = [MenuItemFactory() for _ in range(10)]
        self.order_items = [
            OrderItemFactory(
                order=self.order, item=self.menu_items[random.randint(0, 9)]
            )
            for _ in range(5)
        ]

    def test_object_creation(self):
        self.assertEqual(self.order.customer, "Daniel Grinevich")
        self.assertEqual(self.order.status, "placed")

    def test_model_relationship(self):
        reservation = ReservationFactory()
        self.order.reservation = reservation
        self.assertEqual(self.order.reservation, reservation)

    def test_custom_queryset_method(self):
        OrderFactory(
            customer="Daniel Grinevich", total=32.00, tip=5.00, status="placed"
        )
        placed_orders = Order.get_orders_by_status("placed")
        self.assertTrue("placed" == placed_orders[0].status)

    def test_set_order_total(self):
        self.order.set_order_total()


class OrderItem(TestCase):
    def setUp(self):
        self.order_item = OrderItemFactory()

    def test_model_relationship(self):
        reservation = ReservationFactory()
        menu_items = [MenuItemFactory() for _ in range(10)]
        order = OrderFactory(reservation=reservation)
        order_items = [
            OrderItemFactory(order=order, item=menu_items[random.randint(0, 9)])
            for _ in range(5)
        ]

        test_query = order.orderitem_set.all()

        self.assertTrue(order_items[0].order, order)
        self.assertTrue(len(test_query), len(order_items))
 """
