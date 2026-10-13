"""Regression tests for bugs found in the awards audit."""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import connection
from django.db import transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory
from rest_framework.test import force_authenticate

from navi_backend.awards.api.views import AchievementViewSet
from navi_backend.awards.api.views import MyLoyaltyView
from navi_backend.awards.models import Award
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserAwardLevel
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services import points_service
from navi_backend.awards.tasks import send_award_earned_email
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory
from navi_backend.users.models import User

from .factories import AwardFactory
from .factories import AwardLevelFactory

pytestmark = pytest.mark.django_db


def _completed_order(user, unit_price="10.00"):
    order = OrderFactory(user=user, order_status="O")
    OrderItemFactory(order=order, unit_price=Decimal(unit_price), quantity=1)
    order.order_status = "D"
    order.save(update_fields=["order_status"])
    return order


def test_achievement_progress_handles_leveled_award_without_level(user):
    """A UserAward earned before its award became multi-level has no level;
    /achievements/progress/ used to crash on ``None.name``."""
    award = AwardFactory(slug="converted", threshold=None)
    AwardLevelFactory(award=award, rank=1, name="Bronze", threshold=5)
    UserAward.objects.create(user=user, award=award, level=None)

    request = APIRequestFactory().get("/achievements/progress/")
    force_authenticate(request, user=user)
    response = AchievementViewSet.as_view({"get": "progress"})(request)

    assert response.status_code == 200
    row = next(r for r in response.data if r["id"] == "converted")
    assert row["level"] is None
    assert row["next_level"] == "Bronze"


def test_bonus_points_cascade_into_points_awards(user, loyalty_settings):
    """An award's bonus can cross a TOTAL_POINTS threshold; that badge should
    be earned in the same evaluation, not on the user's *next* order."""
    # TOTAL_SPENT sorts after TOTAL_POINTS, so the points badge is checked
    # before this bonus lands within a single pass.
    AwardFactory(
        rule_type=RuleType.TOTAL_SPENT,
        threshold=1,
        points_reward=100,
    )
    collector = AwardFactory(rule_type=RuleType.TOTAL_POINTS, threshold=100)

    points_service.process_order(_completed_order(user, unit_price="5.00"))

    assert UserAward.objects.filter(user=user, award=collector).exists()


def test_each_crossed_level_is_recorded(user, loyalty_settings):
    award = AwardFactory(rule_type=RuleType.ORDERS_COMPLETED, threshold=None)
    bronze = AwardLevelFactory(award=award, rank=1, threshold=1)
    silver = AwardLevelFactory(award=award, rank=2, threshold=1)
    gold = AwardLevelFactory(award=award, rank=3, threshold=2)

    points_service.process_order(_completed_order(user))
    user_award = UserAward.objects.get(user=user, award=award)
    assert set(user_award.level_history.values_list("level", flat=True)) == {
        bronze.id,
        silver.id,
    }

    points_service.process_order(_completed_order(user))
    assert UserAwardLevel.objects.filter(user_award=user_award).count() == 3
    assert UserAwardLevel.objects.filter(user_award=user_award, level=gold).exists()


def test_no_award_email_when_transaction_rolls_back(
    user,
    loyalty_settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    AwardFactory(rule_type=RuleType.ORDERS_COMPLETED, threshold=1)
    sent = []
    monkeypatch.setattr(
        send_award_earned_email,
        "delay",
        lambda *a, **k: sent.append(a),
    )
    order = _completed_order(user)

    def complete_then_fail():
        with transaction.atomic():
            points_service.process_order(order)
            msg = "boom"
            raise RuntimeError(msg)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(RuntimeError),
    ):
        complete_then_fail()

    assert sent == []
    assert not UserAward.objects.filter(user=user).exists()


def test_process_order_locks_loyalty_row(user, loyalty_settings):
    """Concurrent completions for one user must serialize on the loyalty row,
    otherwise counter/points read-modify-writes lose updates."""
    with CaptureQueriesContext(connection) as ctx:
        points_service.process_order(_completed_order(user))

    loyalty_sql = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
    assert any("awards_userloyalty" in sql for sql in loyalty_sql)


def test_loyalty_dashboard_earned_awards_query_count(
    user,
    django_assert_max_num_queries,
):
    for i in range(5):
        award = AwardFactory(slug=f"lvl-{i}", threshold=None)
        level = AwardLevelFactory(award=award, rank=1, threshold=1)
        UserAward.objects.create(user=user, award=award, level=level)

    request = APIRequestFactory().get("/my/loyalty/")
    force_authenticate(request, user=user)
    # Was 1 + 2 per earned award (levels + level) before prefetching.
    with django_assert_max_num_queries(14):
        response = MyLoyaltyView.as_view()(request)

    assert len(response.data["earned_awards"]) == 5


def test_seed_random_produces_partial_progress():
    call_command("seed_random", users=60, orders=900, seed=7)

    assert Award.objects.exists()
    demo = User.objects.get(email="demo@navi.test")
    assert UserLoyalty.objects.get(user=demo).orders_completed > 0

    levels_reached = {
        ua.level.rank for ua in UserAward.objects.select_related("level") if ua.level
    }
    # A spread of users at different rungs, not everyone maxed out or empty.
    assert {1, 2} <= levels_reached
    leveled = UserAward.objects.filter(level__isnull=False)
    assert UserAwardLevel.objects.filter(user_award__in=leveled).count() >= (
        leveled.count()
    )
