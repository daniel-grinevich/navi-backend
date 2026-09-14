"""Redeeming rewards: the max value cap, the $0 order floor, balances, reversal."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import RedemptionStatus
from navi_backend.awards.models import Reward
from navi_backend.awards.models import RewardRedemption
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.exceptions import InsufficientPointsError
from navi_backend.awards.services.exceptions import RedemptionError
from navi_backend.awards.services.points_service import record_points
from navi_backend.awards.services.redemption_service import apply_redemptions
from navi_backend.awards.services.redemption_service import reverse_order_redemptions
from navi_backend.menu.tests.factories import CategoryFactory
from navi_backend.menu.tests.factories import CustomizationFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.tests.factories import OrderCustomizationFactory
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import RewardFactory
from .factories import UserLoyaltyFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def member(user):
    UserLoyaltyFactory(user=user, balance_points=1000, lifetime_points=1000)
    return user


def _order_with_line(user, price="5.00", quantity=1, menu_item=None):
    order = OrderFactory(user=user, order_status="O", payment=None)
    item = OrderItemFactory(
        order=order,
        menu_item=menu_item or MenuItemFactory(),
        unit_price=Decimal(price),
        quantity=quantity,
    )
    return order, item


def _balance(user):
    return UserLoyalty.objects.get(user=user).balance_points


class TestApplyRedemptions:
    def test_free_drink_under_the_cap(self, member):
        order, item = _order_with_line(member, "5.00")
        reward = RewardFactory(
            menu_item=item.menu_item,
            points_cost=200,
            max_value=Decimal("6.00"),
        )

        [redemption] = apply_redemptions(order, member, [(reward, item)])

        assert redemption.discount_amount == Decimal("5.00")
        assert order.price == Decimal("0.00")
        assert _balance(member) == 800
        entry = PointsTransaction.objects.get(redemption=redemption)
        assert entry.reason == PointsReason.REDEMPTION
        assert entry.points == -200
        assert entry.balance_after == 800

    def test_max_value_caps_the_discount(self, member):
        order, item = _order_with_line(member, "7.50")
        reward = RewardFactory(menu_item=item.menu_item, max_value=Decimal("6.00"))

        [redemption] = apply_redemptions(order, member, [(reward, item)])

        assert redemption.discount_amount == Decimal("6.00")
        assert order.price == Decimal("1.50")

    def test_covers_one_unit_only(self, member):
        order, item = _order_with_line(member, "5.00", quantity=2)
        reward = RewardFactory(menu_item=item.menu_item)

        apply_redemptions(order, member, [(reward, item)])

        assert order.price == Decimal("5.00")

    def test_category_reward_matches_items_in_the_category(self, member):
        category = CategoryFactory()
        order, item = _order_with_line(
            member,
            "4.00",
            menu_item=MenuItemFactory(category=category),
        )
        reward = RewardFactory(menu_item=None, category=category)

        apply_redemptions(order, member, [(reward, item)])

        assert order.price == Decimal("0.00")

    def test_customization_reward_covers_one_unit_of_the_extra(self, member):
        oat = CustomizationFactory()
        order, item = _order_with_line(member, "5.00")
        extra = OrderCustomizationFactory(
            order_item=item,
            customization=oat,
            quantity=2,
            unit_price=Decimal("0.75"),
        )
        reward = RewardFactory(
            menu_item=None,
            customization=oat,
            points_cost=50,
            max_value=Decimal("1.00"),
        )

        apply_redemptions(order, member, [(reward, extra)])

        assert order.subtotal == Decimal("6.50")
        assert order.price == Decimal("5.75")
        assert _balance(member) == 950

    def test_wrong_item_is_rejected(self, member):
        order, item = _order_with_line(member)
        reward = RewardFactory()  # targets some other menu item

        with pytest.raises(RedemptionError, match="can't be used"):
            apply_redemptions(order, member, [(reward, item)])

        assert not RewardRedemption.objects.exists()
        assert _balance(member) == 1000

    def test_not_enough_points_rolls_back(self, user):
        UserLoyaltyFactory(user=user, balance_points=50)
        order, item = _order_with_line(user)
        reward = RewardFactory(menu_item=item.menu_item, points_cost=200)

        with pytest.raises(RedemptionError, match="Not enough points"):
            apply_redemptions(order, user, [(reward, item)])

        assert not RewardRedemption.objects.exists()
        assert not PointsTransaction.objects.exists()
        assert _balance(user) == 50

    def test_a_later_failure_rolls_back_earlier_redemptions(self, user):
        UserLoyaltyFactory(user=user, balance_points=250)
        order, first = _order_with_line(user)
        second = OrderItemFactory(
            order=order,
            menu_item=MenuItemFactory(),
            unit_price=Decimal("5.00"),
        )
        requests = [
            (RewardFactory(menu_item=first.menu_item, points_cost=200), first),
            (RewardFactory(menu_item=second.menu_item, points_cost=200), second),
        ]

        with pytest.raises(RedemptionError):
            apply_redemptions(order, user, requests)

        assert not RewardRedemption.objects.exists()
        assert _balance(user) == 250

    def test_guests_cannot_redeem(self):
        guest = UserFactory(is_guest=True)
        order, item = _order_with_line(guest)
        reward = RewardFactory(menu_item=item.menu_item)

        with pytest.raises(RedemptionError, match="full account"):
            apply_redemptions(order, guest, [(reward, item)])

    @pytest.mark.parametrize(
        "overrides",
        [
            {"status": "I"},
            {"ends_at": timezone.now() - timedelta(minutes=1)},
            {"status": "I", "is_deleted": True},
        ],
        ids=["inactive", "ended", "deleted"],
    )
    def test_reward_must_be_live(self, member, overrides):
        order, item = _order_with_line(member)
        reward = RewardFactory(menu_item=item.menu_item, **overrides)

        with pytest.raises(RedemptionError, match="not available"):
            apply_redemptions(order, member, [(reward, item)])

    def test_one_reward_per_line(self, member):
        order, item = _order_with_line(member)
        reward = RewardFactory(menu_item=item.menu_item, points_cost=10)

        with pytest.raises(RedemptionError, match="Only one reward"):
            apply_redemptions(order, member, [(reward, item), (reward, item)])

    def test_leftover_below_stripe_minimum_is_waived(self, member):
        order, item = _order_with_line(member, "6.30")
        reward = RewardFactory(menu_item=item.menu_item, max_value=Decimal("6.00"))

        [redemption] = apply_redemptions(order, member, [(reward, item)])

        assert redemption.discount_amount == Decimal("6.30")
        assert order.price == Decimal("0.00")

    def test_leftover_at_stripe_minimum_is_still_charged(self, member):
        order, item = _order_with_line(member, "6.50")
        reward = RewardFactory(menu_item=item.menu_item, max_value=Decimal("6.00"))

        [redemption] = apply_redemptions(order, member, [(reward, item)])

        assert redemption.discount_amount == Decimal("6.00")
        assert order.price == Decimal("0.50")

    def test_free_extra_must_cost_something(self, member):
        oat = CustomizationFactory()
        order, item = _order_with_line(member)
        extra = OrderCustomizationFactory(
            order_item=item,
            customization=oat,
            quantity=1,
            unit_price=Decimal("0.00"),
        )
        reward = RewardFactory(menu_item=None, customization=oat)

        with pytest.raises(RedemptionError, match="nothing to take off"):
            apply_redemptions(order, member, [(reward, extra)])


class TestOrderFloor:
    def test_discount_is_capped_by_price_and_max_value(self):
        reward = Reward(max_value=Decimal("6.00"))

        assert reward.discount_for(Decimal("7.50")) == Decimal("6.00")
        assert reward.discount_for(Decimal("5.00")) == Decimal("5.00")
        assert reward.discount_for(Decimal("-1.00")) == Decimal("0.00")

    def test_order_price_never_goes_negative(self, member):
        order, item = _order_with_line(member, "5.00")
        reward = RewardFactory(menu_item=item.menu_item, max_value=Decimal("50.00"))
        # Bypass the service (which caps discounts) to force an over-discount.
        RewardRedemption.objects.create(
            user=member,
            reward=reward,
            order=order,
            order_item=item,
            points_spent=1,
            discount_amount=Decimal("40.00"),
        )

        assert order.subtotal == Decimal("5.00")
        assert order.discount_total == Decimal("40.00")
        assert order.price == Decimal("0.00")
        with pytest.raises(ValidationError):
            order.clean()


class TestConstraints:
    def test_max_value_must_be_positive(self):
        with pytest.raises(ValidationError):
            RewardFactory(max_value=Decimal("0.00"))

        reward = RewardFactory()
        with pytest.raises(IntegrityError), transaction.atomic():
            Reward.objects.filter(pk=reward.pk).update(max_value=Decimal("0.00"))

    def test_reward_needs_exactly_one_target(self):
        with pytest.raises(ValidationError):
            RewardFactory(category=CategoryFactory())  # plus the default menu item
        with pytest.raises(ValidationError):
            RewardFactory(menu_item=None)

    def test_discount_cannot_be_negative(self, member):
        order, item = _order_with_line(member)
        reward = RewardFactory(menu_item=item.menu_item)

        with pytest.raises(IntegrityError), transaction.atomic():
            RewardRedemption.objects.create(
                user=member,
                reward=reward,
                order=order,
                order_item=item,
                points_spent=1,
                discount_amount=Decimal("-1.00"),
            )

    def test_balance_cannot_go_negative(self, user):
        loyalty = UserLoyaltyFactory(user=user, balance_points=10)

        with pytest.raises(InsufficientPointsError):
            record_points(loyalty, -11, PointsReason.ADJUSTMENT)

        loyalty.refresh_from_db()
        assert loyalty.balance_points == 10
        assert not PointsTransaction.objects.exists()


class TestReversal:
    def test_cancel_refunds_points_exactly_once(self, member):
        order, item = _order_with_line(member)
        reward = RewardFactory(menu_item=item.menu_item, points_cost=200)
        apply_redemptions(order, member, [(reward, item)])

        assert reverse_order_redemptions([order.id]) == 1
        assert reverse_order_redemptions([order.id]) == 0

        loyalty = UserLoyalty.objects.get(user=member)
        assert loyalty.balance_points == 1000
        assert loyalty.lifetime_points == 1000  # a refund is not new earning
        redemption = RewardRedemption.objects.get()
        assert redemption.status == RedemptionStatus.REVERSED
        assert redemption.reversed_at is not None
        assert (
            PointsTransaction.objects.filter(
                reason=PointsReason.REDEMPTION_REVERSAL,
            ).count()
            == 1
        )

    def test_reversal_keeps_the_order_discount(self, member):
        order, item = _order_with_line(member, "5.00")
        apply_redemptions(
            order, member, [(RewardFactory(menu_item=item.menu_item), item)]
        )

        reverse_order_redemptions([order.id])

        assert order.price == Decimal("0.00")
