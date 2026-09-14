"""Promotion bonus points: scopes, stacking rules, schedules and ledger entries."""

from datetime import UTC
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal

import pytest

from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import PromotionEffect
from navi_backend.awards.models import PromotionScope
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services import points_service
from navi_backend.awards.services.promotions import promotion_bonuses
from navi_backend.awards.services.redemption_service import apply_redemptions
from navi_backend.menu.tests.factories import CustomizationFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.models import Order
from navi_backend.orders.tests.factories import OrderCustomizationFactory
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import PromotionFactory
from .factories import RewardFactory
from .factories import UserLoyaltyFactory

pytestmark = pytest.mark.django_db

# A Tuesday afternoon (ISO weekday 2) in the project TIME_ZONE (UTC), safely in
# the past so "evaluated at order time" can't coincide with the real clock.
TUESDAY_3PM = datetime(2025, 9, 16, 15, 0, tzinfo=UTC)

FIXED = {"effect": PromotionEffect.FIXED, "multiplier": None}


def _order(user, created_at=TUESDAY_3PM):
    order = OrderFactory(user=user, order_status="O", payment=None)
    Order.objects.filter(pk=order.pk).update(created_at=created_at)
    order.refresh_from_db()
    return order


def _line(order, menu_item, unit_price="10.00", quantity=1):
    return OrderItemFactory(
        order=order,
        menu_item=menu_item,
        unit_price=Decimal(unit_price),
        quantity=quantity,
    )


def _bonuses(order, settings):
    return {
        promotion.name: points
        for promotion, points in promotion_bonuses(order, settings)
    }


def _complete(order):
    order.order_status = "D"
    order.save(update_fields=["order_status"])
    return order


class TestScopesAndStacking:
    def test_no_live_promotions(self, user, loyalty_settings):
        order = _order(user)
        _line(order, MenuItemFactory())

        assert promotion_bonuses(order, loyalty_settings) == []

    def test_item_multiplier_boosts_the_line(self, user, loyalty_settings):
        latte = MenuItemFactory()
        PromotionFactory(
            name="2x latte", scope=PromotionScope.MENU_ITEM, menu_item=latte
        )
        order = _order(user)
        _line(order, latte, "10.00")

        assert _bonuses(order, loyalty_settings) == {"2x latte": 10}

    def test_other_items_do_not_match(self, user, loyalty_settings):
        latte = MenuItemFactory()
        PromotionFactory(scope=PromotionScope.MENU_ITEM, menu_item=latte)
        order = _order(user)
        _line(order, MenuItemFactory(), "10.00")

        assert _bonuses(order, loyalty_settings) == {}

    def test_highest_multiplier_wins_without_stacking(self, user, loyalty_settings):
        latte = MenuItemFactory()
        PromotionFactory(
            name="2x latte",
            scope=PromotionScope.MENU_ITEM,
            menu_item=latte,
            multiplier=Decimal("2.00"),
        )
        PromotionFactory(
            name="3x category",
            scope=PromotionScope.CATEGORY,
            category=latte.category,
            multiplier=Decimal("3.00"),
        )
        PromotionFactory(name="1.5x order", multiplier=Decimal("1.50"))
        order = _order(user)
        _line(order, latte, "10.00")

        # 10 base points; only the 3x promotion pays, for the extra 2x.
        assert _bonuses(order, loyalty_settings) == {"3x category": 20}

    def test_order_wide_multiplier_covers_every_line(self, user, loyalty_settings):
        PromotionFactory(name="double points day")
        order = _order(user)
        _line(order, MenuItemFactory(), "10.00")
        _line(order, MenuItemFactory(), "5.00")

        assert _bonuses(order, loyalty_settings) == {"double points day": 15}

    def test_fixed_bonuses_stack_per_unit(self, user, loyalty_settings):
        latte = MenuItemFactory()
        PromotionFactory(
            name="+5 latte",
            scope=PromotionScope.MENU_ITEM,
            menu_item=latte,
            bonus_points=5,
            **FIXED,
        )
        PromotionFactory(
            name="+3 category",
            scope=PromotionScope.CATEGORY,
            category=latte.category,
            bonus_points=3,
            **FIXED,
        )
        order = _order(user)
        _line(order, latte, "4.00", quantity=2)

        assert _bonuses(order, loyalty_settings) == {"+5 latte": 10, "+3 category": 6}

    def test_fixed_customization_bonus_per_extra(self, user, loyalty_settings):
        oat = CustomizationFactory()
        PromotionFactory(
            name="+4 oat",
            scope=PromotionScope.CUSTOMIZATION,
            customization=oat,
            bonus_points=4,
            **FIXED,
        )
        order = _order(user)
        item = _line(order, MenuItemFactory(), "10.00")
        OrderCustomizationFactory(
            order_item=item,
            customization=oat,
            quantity=2,
            unit_price=Decimal("0.50"),
        )

        assert _bonuses(order, loyalty_settings) == {"+4 oat": 8}

    def test_customization_multiplier_boosts_the_whole_line(
        self, user, loyalty_settings
    ):
        oat = CustomizationFactory()
        PromotionFactory(
            name="2x with oat",
            scope=PromotionScope.CUSTOMIZATION,
            customization=oat,
        )
        order = _order(user)
        item = _line(order, MenuItemFactory(), "10.00")
        OrderCustomizationFactory(
            order_item=item,
            customization=oat,
            quantity=2,
            unit_price=Decimal("0.50"),
        )

        # Line is $10 + 2 x $0.50 = $11 -> 11 points, doubled.
        assert _bonuses(order, loyalty_settings) == {"2x with oat": 11}

    def test_redeemed_units_earn_nothing(self, user, loyalty_settings):
        latte = MenuItemFactory()
        PromotionFactory(
            name="+5 latte",
            scope=PromotionScope.MENU_ITEM,
            menu_item=latte,
            bonus_points=5,
            **FIXED,
        )
        PromotionFactory(name="double points")
        UserLoyaltyFactory(user=user, balance_points=1000)
        order = _order(user)
        item = _line(order, latte, "5.00")
        apply_redemptions(order, user, [(RewardFactory(menu_item=latte), item)])

        assert order.price == Decimal("0.00")
        assert _bonuses(order, loyalty_settings) == {}


class TestOrderWidePromotions:
    def test_minimum_order_total_uses_the_paid_total(self, user, loyalty_settings):
        PromotionFactory(
            name="+25 over $15",
            bonus_points=25,
            min_order_total=Decimal("15.00"),
            **FIXED,
        )
        small = _order(user)
        _line(small, MenuItemFactory(), "10.00")
        big = _order(user)
        _line(big, MenuItemFactory(), "20.00")

        assert _bonuses(small, loyalty_settings) == {}
        assert _bonuses(big, loyalty_settings) == {"+25 over $15": 25}

    def test_first_order_only(self, user, loyalty_settings):
        PromotionFactory(
            name="welcome", bonus_points=50, first_order_only=True, **FIXED
        )
        first = _order(user)
        _line(first, MenuItemFactory(), "10.00")

        assert _bonuses(first, loyalty_settings) == {"welcome": 50}

        OrderFactory(user=user, order_status="D", payment=None)
        assert _bonuses(first, loyalty_settings) == {}


class TestSchedules:
    @pytest.mark.parametrize(
        ("schedule", "expected_live"),
        [
            ({}, True),
            (
                {
                    "starts_at": TUESDAY_3PM - timedelta(days=1),
                    "ends_at": TUESDAY_3PM + timedelta(days=1),
                },
                True,
            ),
            ({"starts_at": TUESDAY_3PM + timedelta(minutes=1)}, False),
            ({"ends_at": TUESDAY_3PM}, False),
            ({"days_of_week": [2]}, True),
            ({"days_of_week": [1, 3]}, False),
            ({"start_time": time(14, 0), "end_time": time(17, 0)}, True),
            ({"start_time": time(15, 30)}, False),
            ({"end_time": time(15, 0)}, False),
            ({"status": "I"}, False),
            ({"status": "I", "is_deleted": True}, False),
        ],
        ids=[
            "always-on",
            "inside-date-range",
            "not-started",
            "end-is-exclusive",
            "right-weekday",
            "wrong-weekday",
            "inside-daily-window",
            "before-daily-start",
            "daily-end-is-exclusive",
            "inactive",
            "deleted",
        ],
    )
    def test_live_window(self, user, loyalty_settings, schedule, expected_live):
        PromotionFactory(name="deal", **schedule)
        order = _order(user)
        _line(order, MenuItemFactory(), "10.00")

        assert bool(_bonuses(order, loyalty_settings)) is expected_live

    def test_evaluated_when_the_customer_ordered(self, user, loyalty_settings):
        # Happy hour ended long ago, but the order was placed during it.
        PromotionFactory(
            name="happy hour",
            starts_at=TUESDAY_3PM - timedelta(hours=1),
            ends_at=TUESDAY_3PM + timedelta(hours=1),
        )
        order = _order(user)
        _line(order, MenuItemFactory(), "10.00")

        assert _bonuses(order, loyalty_settings) == {"happy hour": 10}


class TestProcessOrderWithPromotions:
    def test_records_a_bonus_entry_per_promotion(self, user, loyalty_settings):
        PromotionFactory(name="double points")
        order = _order(user)
        _line(order, MenuItemFactory(), "10.00")

        result = points_service.process_order(_complete(order))

        assert result["base_points"] == 10
        assert result["bonus_points"] == 10
        assert result["points_awarded"] == 20
        loyalty = UserLoyalty.for_user(user)
        assert loyalty.lifetime_points == 20
        assert loyalty.balance_points == 20
        bonus = PointsTransaction.objects.get(
            order=order,
            reason=PointsReason.PROMOTION_BONUS,
        )
        assert bonus.points == 10
        assert bonus.promotion.name == "double points"

    def test_retry_does_not_double_grant(self, user, loyalty_settings):
        PromotionFactory()
        order = _order(user)
        _line(order, MenuItemFactory(), "10.00")
        _complete(order)

        points_service.process_order(order)
        assert points_service.process_order(order) is None

        assert PointsTransaction.objects.filter(order=order).count() == 2
        assert UserLoyalty.for_user(user).lifetime_points == 20

    def test_guest_orders_earn_nothing(self, loyalty_settings):
        guest = UserFactory(is_guest=True)
        PromotionFactory()
        order = _order(guest)
        _line(order, MenuItemFactory(), "10.00")

        assert points_service.process_order(_complete(order)) is None
        assert not PointsTransaction.objects.exists()

    def test_fully_redeemed_order_is_still_marked_processed(
        self, user, loyalty_settings
    ):
        latte = MenuItemFactory()
        UserLoyaltyFactory(user=user, balance_points=1000)
        order = _order(user)
        item = _line(order, latte, "5.00")
        apply_redemptions(order, user, [(RewardFactory(menu_item=latte), item)])
        _complete(order)

        points_service.process_order(order)
        points_service.process_order(order)

        loyalty = UserLoyalty.for_user(user)
        assert loyalty.orders_completed == 1
        entry = PointsTransaction.objects.get(order=order, reason=PointsReason.ORDER)
        assert entry.points == 0
