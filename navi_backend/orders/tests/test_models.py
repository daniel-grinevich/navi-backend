from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.menu.tests.factories import CustomizationFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.payments.tests.factories import PaymentFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import OrderCustomizationFactory
from .factories import OrderFactory
from .factories import OrderItemFactory

User = get_user_model()


class TestOrder:
    def test_create_order(self, order):
        assert order
        assert order.user
        assert order.navi_port
        assert order.payment
        assert order.order_status == "O"
        assert order.slug

    def test_order_string_representation(self):
        user = UserFactory(email="test@example.com")
        order = OrderFactory(user=user)
        assert str(order) == f"{user} (v{order.created_at})"

    def test_order_with_user(self):
        user = UserFactory(email="test@example.com")
        order = OrderFactory(user=user)
        assert order.user == user
        assert order.user.email == "test@example.com"

    def test_order_with_navi_port(self):
        navi_port = NaviPortFactory(name="Port 1")
        order = OrderFactory(navi_port=navi_port)
        assert order.navi_port == navi_port
        assert order.navi_port.name == "Port 1"

    def test_order_with_payment(self):
        payment = PaymentFactory()
        order = OrderFactory(payment=payment)
        assert order.payment == payment

    def test_order_status_choices(self):
        # Test different status values
        order = OrderFactory(order_status="O")  # Ordered
        assert order.order_status == "O"

        order.order_status = "S"  # Sent
        order.save()
        assert order.order_status == "S"

    def test_order_price_calculation(self):
        """Test that order can calculate total price from its items"""
        order = OrderFactory()

        # Add some order items
        item1 = OrderItemFactory(order=order, quantity=2, unit_price=Decimal("10.00"))
        item2 = OrderItemFactory(order=order, quantity=1, unit_price=Decimal("15.00"))

        # Test the price property which should calculate from all items
        expected_total = item1.price + item2.price
        assert order.price == expected_total


class TestOrderItem:
    def test_create_order_item(self, order_item):
        assert order_item
        assert order_item.order
        assert order_item.menu_item
        assert order_item.quantity > 0
        assert order_item.unit_price > 0
        assert order_item.slug

    def test_order_item_string_representation(self):
        order = OrderFactory()
        menu_item = MenuItemFactory(name="Latte")
        order_item = OrderItemFactory(order=order, menu_item=menu_item)
        expected = f"{order} {menu_item}"
        assert str(order_item) == expected

    def test_order_item_price_calculation(self):
        """Test that order item calculates price including customizations"""
        order_item = OrderItemFactory(quantity=2, unit_price=Decimal("10.00"))

        # Add customizations
        OrderCustomizationFactory(
            order_item=order_item, quantity=1, unit_price=Decimal("2.50")
        )
        OrderCustomizationFactory(
            order_item=order_item, quantity=2, unit_price=Decimal("1.00")
        )

        # Item total: 2 * 10.00 = 20.00
        # Customization total: (1 * 2.50) + (2 * 1.00) = 4.50
        # Expected total: 24.50

        expected_total = Decimal("24.50")
        assert order_item.price == expected_total

    def test_order_item_with_customizations(self):
        order_item = OrderItemFactory()

        # Add customizations
        customization1 = OrderCustomizationFactory(
            order_item=order_item, quantity=1, unit_price=Decimal("2.50")
        )
        customization2 = OrderCustomizationFactory(
            order_item=order_item, quantity=2, unit_price=Decimal("1.00")
        )

        customizations = order_item.customizations.all()
        assert len(customizations) == 2
        assert customization1 in customizations
        assert customization2 in customizations

    def test_order_item_validation_requires_order(self):
        """Test that saving without an order raises ValidationError"""
        order_item = OrderItemFactory.build(order=None)
        with pytest.raises(ValidationError) as exc_info:
            order_item.save()
        assert "Can't save an order item without a parent order" in str(exc_info.value)

    def test_order_item_validation_order_status(self):
        """Test that updating items is only allowed for 'Ordered' status"""
        order = OrderFactory(order_status="S")  # Sent status
        order_item = OrderItemFactory.build(order=order)

        with pytest.raises(ValidationError) as exc_info:
            order_item.save()
        assert (
            "You can't update order items if the order is not in 'Ordered' status"
            in str(exc_info.value)
        )

    def test_order_item_auto_set_unit_price(self):
        """Test that unit price is set from menu item if not provided"""
        menu_item = MenuItemFactory(price=Decimal("15.99"))
        order_item = OrderItemFactory.build(menu_item=menu_item, unit_price=None)
        order_item.save()

        assert order_item.unit_price == menu_item.price


class TestOrderCustomization:
    def test_create_order_customization(self, order_customization):
        assert order_customization
        assert order_customization.order_item
        assert order_customization.customization
        assert order_customization.quantity > 0
        assert order_customization.unit_price > 0
        assert order_customization.slug

    def test_order_customization_string_representation(self):
        order_item = OrderItemFactory()
        customization = CustomizationFactory(name="Extra Shot")
        order_customization = OrderCustomizationFactory(
            order_item=order_item, customization=customization
        )
        expected = f"{order_item} {customization}"
        assert str(order_customization) == expected

    def test_order_customization_price_calculation(self):
        order_customization = OrderCustomizationFactory(
            quantity=3, unit_price=Decimal("1.50")
        )
        expected_price = Decimal("4.50")  # 3 * 1.50
        assert order_customization.price == expected_price

    def test_order_customization_relationship_to_order_item(self):
        order_item = OrderItemFactory()
        customization = CustomizationFactory()

        order_customization = OrderCustomizationFactory(
            order_item=order_item, customization=customization
        )

        assert order_customization.order_item == order_item
        assert order_customization.customization == customization
        assert order_customization in order_item.customizations.all()

    def test_order_customization_validation_order_status(self):
        """Test that updating customizations is only allowed for 'Ordered' status"""
        order = OrderFactory(order_status="S")  # Sent status
        order_item = OrderItemFactory(order=order)
        order_customization = OrderCustomizationFactory.build(order_item=order_item)

        with pytest.raises(ValidationError) as exc_info:
            order_customization.save()
        assert (
            "You can't update order customizations if the"
            "order is not in 'Ordered' status" in str(exc_info.value)
        )


class TestOrderWorkflow:
    def test_complete_order_creation_workflow(self):
        """Test creating a complete order with items and customizations"""
        # Create order
        user = UserFactory()
        navi_port = NaviPortFactory()
        payment = PaymentFactory()

        order = OrderFactory(
            user=user, navi_port=navi_port, payment=payment, order_status="O"
        )

        # Add order items
        menu_item1 = MenuItemFactory(name="Latte", price=Decimal("4.50"))
        menu_item2 = MenuItemFactory(name="Espresso", price=Decimal("3.00"))

        order_item1 = OrderItemFactory(
            order=order, menu_item=menu_item1, quantity=2, unit_price=menu_item1.price
        )

        order_item2 = OrderItemFactory(
            order=order, menu_item=menu_item2, quantity=1, unit_price=menu_item2.price
        )

        # Add customizations
        customization = CustomizationFactory(name="Extra Shot", price=Decimal("1.00"))
        OrderCustomizationFactory(
            order_item=order_item1,
            customization=customization,
            quantity=2,
            unit_price=customization.price,
        )

        # Verify relationships
        assert order.items.count() == 2
        assert order_item1.customizations.count() == 1
        assert order_item2.customizations.count() == 0

        # Verify price calculation using the model's price properties
        expected_item1_price = (2 * Decimal("4.50")) + (2 * Decimal("1.00"))  # 11.00
        expected_item2_price = 1 * Decimal("3.00")  # 3.00
        expected_total = expected_item1_price + expected_item2_price  # 14.00

        assert order_item1.price == expected_item1_price
        assert order_item2.price == expected_item2_price
        assert order.price == expected_total
