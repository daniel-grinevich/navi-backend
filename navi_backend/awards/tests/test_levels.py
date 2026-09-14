"""Multi-level badges: progressive levels on a single award, plus the
generic (non-order) re-evaluation task."""

from decimal import Decimal

import pytest

from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services import points_service
from navi_backend.awards.tasks import evaluate_user_awards
from navi_backend.awards.tasks import send_award_earned_email
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory

from .factories import AwardFactory
from .factories import AwardLevelFactory

pytestmark = pytest.mark.django_db


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


def _leveled_award(**kwargs):
    award = AwardFactory(
        rule_type=RuleType.ORDERS_COMPLETED,
        threshold=None,
        **kwargs,
    )
    bronze = AwardLevelFactory(award=award, rank=1, name="Bronze", threshold=1)
    silver = AwardLevelFactory(
        award=award,
        rank=2,
        name="Silver",
        threshold=2,
        points_reward=25,
    )
    gold = AwardLevelFactory(award=award, rank=3, name="Gold", threshold=5)
    return award, bronze, silver, gold


class TestLeveledAwards:
    def test_first_level_earned(self, user, loyalty_settings):
        award, bronze, *_ = _leveled_award()

        result = points_service.process_order(_completed_order(user))

        assert award in result["awards"]
        user_award = UserAward.objects.get(user=user, award=award)
        assert user_award.level == bronze

    def test_level_upgrades_on_next_threshold(self, user, loyalty_settings):
        award, _, silver, _ = _leveled_award()

        points_service.process_order(_completed_order(user))
        points_service.process_order(_completed_order(user))

        user_award = UserAward.objects.get(user=user, award=award)
        assert user_award.level == silver
        # Still one row per user/award — the badge upgrades, not duplicates.
        assert UserAward.objects.filter(user=user, award=award).count() == 1

    def test_skipping_levels_grants_all_crossed_bonuses(
        self,
        user,
        loyalty_settings,
    ):
        award = AwardFactory(rule_type=RuleType.TOTAL_SPENT, threshold=None)
        AwardLevelFactory(
            award=award,
            rank=1,
            name="Bronze",
            threshold=10,
            points_reward=5,
        )
        silver = AwardLevelFactory(
            award=award,
            rank=2,
            name="Silver",
            threshold=20,
            points_reward=10,
        )

        # One $25 order crosses both thresholds at once.
        points_service.process_order(_completed_order(user, "25.00", 1))

        user_award = UserAward.objects.get(user=user, award=award)
        assert user_award.level == silver
        bonus = PointsTransaction.objects.get(
            user=user,
            reason=PointsReason.AWARD_BONUS,
        )
        assert bonus.points == 15  # both level bonuses in one grant

    def test_no_regrant_when_level_unchanged(self, user, loyalty_settings):
        award, *_ = _leveled_award()

        points_service.process_order(_completed_order(user))
        loyalty = UserLoyalty.for_user(user)
        result = points_service.evaluate_awards(loyalty)

        assert result == []
        assert UserAward.objects.filter(user=user, award=award).count() == 1

    def test_level_notification_includes_level(
        self,
        user,
        loyalty_settings,
        monkeypatch,
    ):
        _, bronze, *_ = _leveled_award()

        sent = []
        monkeypatch.setattr(
            send_award_earned_email,
            "delay",
            lambda *a, **k: sent.append(a),
        )

        points_service.process_order(_completed_order(user))

        assert len(sent) == 1
        assert sent[0][2] == str(bronze.id)


class TestEvaluateUserAwardsTask:
    def test_earns_award_without_an_order(self, user, loyalty_settings):
        """The generic trigger grants awards for non-order metrics —
        e.g. a badge on lifetime points adjusted manually."""
        award = AwardFactory(rule_type=RuleType.TOTAL_POINTS, threshold=10)
        loyalty = UserLoyalty.for_user(user)
        loyalty.lifetime_points = 10
        loyalty.save(update_fields=["lifetime_points"])

        evaluate_user_awards(str(user.id))

        assert UserAward.objects.filter(user=user, award=award).exists()

    def test_unknown_user_is_a_noop(self, loyalty_settings):
        evaluate_user_awards(999999999)

    def test_idempotent(self, user, loyalty_settings):
        award = AwardFactory(rule_type=RuleType.TOTAL_POINTS, threshold=10)
        loyalty = UserLoyalty.for_user(user)
        loyalty.lifetime_points = 10
        loyalty.save(update_fields=["lifetime_points"])

        evaluate_user_awards(str(user.id))
        evaluate_user_awards(str(user.id))

        assert UserAward.objects.filter(user=user, award=award).count() == 1
