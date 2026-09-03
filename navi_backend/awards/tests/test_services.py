from decimal import Decimal

import pytest

from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services import points_service
from navi_backend.awards.tasks import send_award_earned_email
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory

from .factories import AwardFactory
from .factories import TierFactory


def _completed_order(user, unit_price="10.00", quantity=1):
    order = OrderFactory(user=user, order_status="O")
    OrderItemFactory(
        order=order,
        unit_price=Decimal(unit_price),
        quantity=quantity,
    )
    order.order_status = "D"
    order.save(update_fields=["order_status"])
    return order


@pytest.mark.django_db
class TestProcessOrder:
    def test_grants_points_and_updates_counters(self, user, loyalty_settings):
        order = _completed_order(user, unit_price="10.00", quantity=2)  # $20

        result = points_service.process_order(order)

        loyalty = UserLoyalty.for_user(user)
        assert result["points_awarded"] == 20
        assert loyalty.lifetime_points == 20
        assert loyalty.balance_points == 20
        assert loyalty.orders_completed == 1
        assert loyalty.total_spent == Decimal("20.00")
        assert (
            PointsTransaction.objects.filter(
                order=order,
                reason=PointsReason.ORDER,
            ).count()
            == 1
        )

    def test_points_per_order_bonus(self, user, loyalty_settings):
        loyalty_settings.points_per_order = 5
        loyalty_settings.save()
        order = _completed_order(user, unit_price="10.00", quantity=1)  # $10

        result = points_service.process_order(order)

        assert result["points_awarded"] == 15  # 10 * 1 + 5

    def test_is_idempotent(self, user, loyalty_settings):
        order = _completed_order(user, unit_price="10.00", quantity=1)

        points_service.process_order(order)
        second = points_service.process_order(order)

        loyalty = UserLoyalty.for_user(user)
        assert second is None
        assert loyalty.orders_completed == 1
        assert loyalty.lifetime_points == 10

    def test_guest_order_skipped(self, loyalty_settings):
        order = OrderFactory(user=None, order_status="O")
        assert points_service.process_order(order) is None


@pytest.mark.django_db
class TestAwards:
    def test_award_earned_on_threshold(self, user, loyalty_settings):
        award = AwardFactory(
            rule_type=RuleType.ORDERS_COMPLETED,
            threshold=1,
        )
        order = _completed_order(user)

        result = points_service.process_order(order)

        assert award in result["awards"]
        assert UserAward.objects.filter(user=user, award=award).exists()

    def test_award_not_earned_below_threshold(self, user, loyalty_settings):
        AwardFactory(rule_type=RuleType.ORDERS_COMPLETED, threshold=5)
        order = _completed_order(user)

        result = points_service.process_order(order)

        assert result["awards"] == []
        assert not UserAward.objects.filter(user=user).exists()

    def test_award_grants_bonus_points(self, user, loyalty_settings):
        AwardFactory(
            rule_type=RuleType.ORDERS_COMPLETED,
            threshold=1,
            points_reward=50,
        )
        order = _completed_order(user, unit_price="10.00", quantity=1)  # 10 pts

        points_service.process_order(order)

        loyalty = UserLoyalty.for_user(user)
        assert loyalty.lifetime_points == 60  # 10 order + 50 bonus
        assert (
            PointsTransaction.objects.filter(
                user=user,
                reason=PointsReason.AWARD_BONUS,
            ).count()
            == 1
        )

    def test_award_earned_only_once(self, user, loyalty_settings):
        award = AwardFactory(rule_type=RuleType.ORDERS_COMPLETED, threshold=1)

        points_service.process_order(_completed_order(user))
        points_service.process_order(_completed_order(user))

        assert UserAward.objects.filter(user=user, award=award).count() == 1

    def test_total_spent_award(self, user, loyalty_settings):
        award = AwardFactory(rule_type=RuleType.TOTAL_SPENT, threshold=15)

        points_service.process_order(_completed_order(user, "20.00", 1))

        assert UserAward.objects.filter(user=user, award=award).exists()

    def test_distinct_items_award(self, user, loyalty_settings):
        award = AwardFactory(rule_type=RuleType.DISTINCT_ITEMS, threshold=2)

        order = OrderFactory(user=user, order_status="O")
        OrderItemFactory(order=order, unit_price=Decimal("5.00"), quantity=1)
        OrderItemFactory(order=order, unit_price=Decimal("5.00"), quantity=1)
        order.order_status = "D"
        order.save(update_fields=["order_status"])

        points_service.process_order(order)

        assert UserAward.objects.filter(user=user, award=award).exists()


@pytest.mark.django_db
class TestTiers:
    def test_tier_assigned_to_highest_qualifying(self, user, loyalty_settings):
        TierFactory(name="Bronze", threshold_points=0, rank=1)
        silver = TierFactory(name="Silver", threshold_points=15, rank=2)
        TierFactory(name="Gold", threshold_points=1000, rank=3)

        order = _completed_order(user, unit_price="20.00", quantity=1)  # 20 pts
        result = points_service.process_order(order)

        loyalty = UserLoyalty.for_user(user)
        assert loyalty.current_tier == silver
        assert result["tier"] == silver

    def test_no_tier_when_none_qualify(self, user, loyalty_settings):
        TierFactory(name="Gold", threshold_points=1000, rank=3)

        order = _completed_order(user, unit_price="10.00", quantity=1)
        points_service.process_order(order)

        loyalty = UserLoyalty.for_user(user)
        assert loyalty.current_tier is None


@pytest.mark.django_db
class TestNotificationGating:
    def test_no_notification_when_global_off(
        self,
        user,
        loyalty_settings,
        monkeypatch,
    ):
        loyalty_settings.notifications_enabled = False
        loyalty_settings.save()
        AwardFactory(rule_type=RuleType.ORDERS_COMPLETED, threshold=1)

        sent = []
        monkeypatch.setattr(
            send_award_earned_email,
            "delay",
            lambda *a, **k: sent.append(a),
        )

        points_service.process_order(_completed_order(user))
        assert sent == []

    def test_no_notification_when_user_opted_out(
        self,
        user,
        loyalty_settings,
        monkeypatch,
    ):
        AwardFactory(rule_type=RuleType.ORDERS_COMPLETED, threshold=1)
        loyalty = UserLoyalty.for_user(user)
        loyalty.notifications_enabled = False
        loyalty.save()

        sent = []
        monkeypatch.setattr(
            send_award_earned_email,
            "delay",
            lambda *a, **k: sent.append(a),
        )

        points_service.process_order(_completed_order(user))
        assert sent == []

    def test_notification_sent_when_enabled(
        self,
        user,
        loyalty_settings,
        monkeypatch,
    ):
        AwardFactory(rule_type=RuleType.ORDERS_COMPLETED, threshold=1)

        sent = []
        monkeypatch.setattr(
            send_award_earned_email,
            "delay",
            lambda *a, **k: sent.append(a),
        )

        points_service.process_order(_completed_order(user))
        assert len(sent) == 1
