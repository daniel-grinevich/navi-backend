from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from navi_backend.menu.tests.factories import CustomizationFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import OrderCustomizationFactory
from .factories import OrderFactory
from .factories import OrderItemFactory


@pytest.mark.django_db
class TestOrder:
    def test_order_string_representation(self):
        user = UserFactory(email="test@example.com")
        order = OrderFactory(user=user)
        assert str(order) == f"{user} (v{order.created_at})"

    def test_order_price_calculation(self):
        """Test that order can calculate total price from its items"""
        order = OrderFactory()

        item1 = OrderItemFactory(order=order, quantity=2, unit_price=Decimal("10.00"))
        item2 = OrderItemFactory(order=order, quantity=1, unit_price=Decimal("15.00"))

        expected_total = item1.price + item2.price
        assert order.price == expected_total


@pytest.mark.django_db
class TestOrderItem:
    def test_order_item_string_representation(self):
        order = OrderFactory()
        menu_item = MenuItemFactory(name="Latte")
        order_item = OrderItemFactory(order=order, menu_item=menu_item)
        expected = f"{order} {menu_item}"
        assert str(order_item) == expected

    def test_order_item_price_calculation(self):
        """Test that order item calculates price including customizations"""
        order_item = OrderItemFactory(quantity=2, unit_price=Decimal("10.00"))

        OrderCustomizationFactory(
            order_item=order_item, quantity=1, unit_price=Decimal("2.50")
        )
        OrderCustomizationFactory(
            order_item=order_item, quantity=2, unit_price=Decimal("1.00")
        )

        # Item total: 2 * 10.00 = 20.00
        # Customization total: (1 * 2.50) + (2 * 1.00) = 4.50
        expected_total = Decimal("24.50")
        assert order_item.price == expected_total

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
        order_item = OrderItemFactory(menu_item=menu_item, unit_price=None)

        assert order_item.unit_price == menu_item.price


@pytest.mark.django_db
class TestOrderCustomization:
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

    def test_order_customization_validation_order_status(self):
        """Test that updating customizations is only allowed for 'Ordered' status"""
        order = OrderFactory(order_status="O")
        order_item = OrderItemFactory(order=order)
        order.order_status = "S"
        order.save()
        order_customization = OrderCustomizationFactory.build(order_item=order_item)

        with pytest.raises(ValidationError) as exc_info:
            order_customization.save()
        assert (
            "You cannot update order customizations if the order is not in "
            "'Ordered' status." in str(exc_info.value)
        )
