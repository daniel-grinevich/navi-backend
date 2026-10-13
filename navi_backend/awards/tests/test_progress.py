"""``GET /api/my/achievements/progress/`` — per-user badge progress contract."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.awards.models import RuleType
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserAwardLevel
from navi_backend.awards.models import UserLoyalty
from navi_backend.users.tests.factories import UserFactory

from .factories import AwardFactory
from .factories import AwardLevelFactory
from .factories import TierFactory

pytestmark = pytest.mark.django_db

URL = reverse("api:my-achievements-progress")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def _set_orders(user, count):
    loyalty = UserLoyalty.for_user(user)
    loyalty.orders_completed = count
    loyalty.save(update_fields=["orders_completed"])
    return loyalty


def _regular():
    award = AwardFactory(
        slug="regular",
        name="Regular",
        description="Keep coming back",
        rule_type=RuleType.ORDERS_COMPLETED,
        threshold=None,
        icon="coffee",
    )
    levels = [
        AwardLevelFactory(award=award, rank=1, name="Bronze", threshold=3),
        AwardLevelFactory(award=award, rank=2, name="Silver", threshold=10),
        AwardLevelFactory(award=award, rank=3, name="Gold", threshold=25),
    ]
    return award, levels


def _row(response, slug):
    return next(r for r in response.data["results"] if r["slug"] == slug)


class TestAuth:
    def test_unauthenticated_is_401(self):
        response = APIClient().get(URL)
        assert response.status_code == 401

    def test_guest_user_allowed(self):
        guest = UserFactory(is_guest=True)
        api = APIClient()
        api.force_authenticate(guest)
        assert api.get(URL).status_code == 200


class TestLeveledRow:
    def test_level_zero(self, user, client):
        _regular()
        _set_orders(user, 2)

        row = _row(client.get(URL), "regular")

        assert row["level"] == 0
        assert row["max_level"] == 3
        assert row["current_value"] == 2
        assert row["prev_threshold"] == 0
        assert row["next_threshold"] == 3
        assert row["earned_at"] is None
        assert row["unit"] == "orders"
        assert row["category"] == "habits"
        assert row["icon"] == "coffee"
        assert [lvl["earned_at"] for lvl in row["levels"]] == [None, None, None]

    def test_mid_ladder_uses_per_level_history(self, user, client):
        award, (bronze, silver, _gold) = _regular()
        _set_orders(user, 12)
        bronze_at = timezone.now() - timedelta(days=30)
        silver_at = timezone.now() - timedelta(days=2)
        user_award = UserAward.objects.create(user=user, award=award, level=silver)
        UserAwardLevel.objects.create(
            user_award=user_award, level=bronze, earned_at=bronze_at
        )
        UserAwardLevel.objects.create(
            user_award=user_award, level=silver, earned_at=silver_at
        )

        row = _row(client.get(URL), "regular")

        assert row["id"] == str(award.id)
        assert row["level"] == 2
        assert row["current_value"] == 12
        assert row["prev_threshold"] == 10
        assert row["next_threshold"] == 25
        assert row["earned_at"] == silver_at.isoformat().replace("+00:00", "Z")
        assert [lvl["level"] for lvl in row["levels"]] == [1, 2, 3]
        assert [lvl["name"] for lvl in row["levels"]] == ["Bronze", "Silver", "Gold"]
        assert [lvl["threshold"] for lvl in row["levels"]] == [3, 10, 25]
        assert row["levels"][0]["earned_at"] is not None
        assert row["levels"][2]["earned_at"] is None

    def test_levels_without_history_fall_back_to_first_earned(self, user, client):
        award, (_bronze, silver, _gold) = _regular()
        _set_orders(user, 12)
        user_award = UserAward.objects.create(user=user, award=award, level=silver)

        row = _row(client.get(URL), "regular")

        assert row["level"] == 2
        assert row["levels"][0]["earned_at"] is not None
        assert row["levels"][1]["earned_at"] == row["earned_at"]
        assert row["earned_at"] is not None
        assert user_award.earned_at is not None

    def test_max_level_has_no_next_threshold(self, user, client):
        award, (*_, gold) = _regular()
        _set_orders(user, 30)
        UserAward.objects.create(user=user, award=award, level=gold)

        row = _row(client.get(URL), "regular")

        assert row["level"] == 3
        assert row["prev_threshold"] == 25
        assert row["next_threshold"] is None

    def test_level_positions_ignore_rank_gaps(self, user, client):
        award = AwardFactory(slug="gappy", threshold=None)
        AwardLevelFactory(award=award, rank=10, name="A", threshold=1)
        top = AwardLevelFactory(award=award, rank=20, name="B", threshold=2)
        _set_orders(user, 2)
        UserAward.objects.create(user=user, award=award, level=top)

        row = _row(client.get(URL), "gappy")

        assert row["level"] == 2
        assert row["max_level"] == 2


class TestFlatRow:
    def test_flat_award_is_a_one_level_ladder(self, user, client):
        award = AwardFactory(
            slug="first-sip",
            name="First Sip",
            rule_type=RuleType.ORDERS_COMPLETED,
            threshold=1,
            category="milestones",
        )
        _set_orders(user, 1)
        UserAward.objects.create(user=user, award=award)

        row = _row(client.get(URL), "first-sip")

        assert row["level"] == 1
        assert row["max_level"] == 1
        assert row["prev_threshold"] == 1
        assert row["next_threshold"] is None
        assert row["category"] == "milestones"
        assert row["levels"] == [
            {
                "level": 1,
                "name": "First Sip",
                "threshold": 1,
                "earned_at": row["earned_at"],
            },
        ]

    def test_unearned_flat_award(self, client):
        AwardFactory(slug="spender", rule_type=RuleType.TOTAL_SPENT, threshold=50)

        row = _row(client.get(URL), "spender")

        assert row["level"] == 0
        assert row["next_threshold"] == 50
        assert row["unit"] == "dollars"
        assert row["category"] == "loyalty"

    def test_excludes_inactive_and_unearnable_awards(self, client):
        AwardFactory(slug="hidden", status="I")
        AwardFactory(slug="broken", threshold=None)  # no threshold, no levels

        slugs = {r["slug"] for r in client.get(URL).data["results"]}

        assert "hidden" not in slugs
        assert "broken" not in slugs


class TestSummary:
    def test_points_tier_and_badge_counts(self, user, client):
        TierFactory(slug="bronze", name="Bronze", threshold_points=0)
        TierFactory(slug="silver", name="Silver", threshold_points=250)
        TierFactory(slug="gold", name="Gold", threshold_points=500)
        award, (bronze, *_) = _regular()
        AwardFactory(slug="other", threshold=100)
        UserAward.objects.create(user=user, award=award, level=bronze)
        loyalty = _set_orders(user, 3)
        loyalty.lifetime_points = 340
        loyalty.save(update_fields=["lifetime_points"])

        summary = client.get(URL).data["summary"]

        assert summary == {
            "points": 340,
            "tier": {"slug": "silver", "name": "Silver", "min_points": 250},
            "next_tier": {"slug": "gold", "name": "Gold", "min_points": 500},
            "badges_earned": 1,
            "badges_total": 2,
        }

    def test_top_tier_has_no_next(self, user, client):
        TierFactory(slug="gold", name="Gold", threshold_points=500)
        loyalty = UserLoyalty.for_user(user)
        loyalty.lifetime_points = 900
        loyalty.save(update_fields=["lifetime_points"])

        summary = client.get(URL).data["summary"]

        assert summary["tier"]["slug"] == "gold"
        assert summary["next_tier"] is None

    def test_below_first_tier(self, client):
        TierFactory(slug="silver", name="Silver", threshold_points=250)

        summary = client.get(URL).data["summary"]

        assert summary["points"] == 0
        assert summary["tier"] is None
        assert summary["next_tier"]["slug"] == "silver"


def test_query_count_is_flat(user, client, django_assert_max_num_queries):
    for i in range(5):
        award = AwardFactory(slug=f"a{i}", threshold=None)
        level = AwardLevelFactory(award=award, rank=1, threshold=1)
        AwardLevelFactory(award=award, rank=2, threshold=5)
        UserAward.objects.create(user=user, award=award, level=level)
    _set_orders(user, 2)

    with django_assert_max_num_queries(10):
        response = client.get(URL)

    assert len(response.data["results"]) == 5
