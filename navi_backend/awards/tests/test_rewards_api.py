"""Customer-facing rewards endpoints: catalog, promotions, redemptions, dashboard."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.awards.models import PROMOTIONS_CACHE_NAMESPACE
from navi_backend.awards.models import REWARDS_CACHE_NAMESPACE
from navi_backend.awards.models import RewardRedemption
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import PromotionFactory
from .factories import RewardFactory
from .factories import UserLoyaltyFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_for():
    def _client(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client


def _redemption(user, reward):
    order = OrderFactory(user=user, order_status="O", payment=None)
    item = OrderItemFactory(
        order=order, menu_item=reward.menu_item, unit_price=Decimal("5.00")
    )
    return RewardRedemption.objects.create(
        user=user,
        reward=reward,
        order=order,
        order_item=item,
        points_spent=reward.points_cost,
        discount_amount=Decimal("5.00"),
    )


class TestRewardCatalog:
    def test_lists_live_rewards_with_affordable_flag(self, user, client_for):
        UserLoyaltyFactory(user=user, balance_points=150)
        cheap = RewardFactory(points_cost=100)
        pricey = RewardFactory(points_cost=500)
        RewardFactory(status="I")
        RewardFactory(starts_at=timezone.now() + timedelta(days=1))

        resp = client_for(user).get("/api/rewards/")

        assert resp.status_code == 200
        affordable = {row["id"]: row["affordable"] for row in resp.data}
        assert affordable == {str(cheap.id): True, str(pricey.id): False}
        row = next(row for row in resp.data if row["id"] == str(cheap.id))
        assert row["max_value"] == "6.00"
        assert row["target_type"] == "menu_item"

    def test_users_without_points_can_afford_nothing(self, user, client_for):
        RewardFactory(points_cost=1)

        resp = client_for(user).get("/api/rewards/")

        assert [row["affordable"] for row in resp.data] == [False]

    def test_requires_authentication(self):
        assert APIClient().get("/api/rewards/").status_code in (401, 403)


class TestPromotionsList:
    def test_lists_only_running_promotions(self, user, client_for):
        running = PromotionFactory()
        PromotionFactory(ends_at=timezone.now() - timedelta(hours=1))

        resp = client_for(user).get("/api/promotions/")

        assert resp.status_code == 200
        assert [row["id"] for row in resp.data] == [str(running.id)]


class TestMyRedemptions:
    def test_lists_only_own_redemptions(self, user, client_for):
        reward = RewardFactory()
        mine = _redemption(user, reward)
        _redemption(UserFactory(), reward)

        resp = client_for(user).get("/api/my/redemptions/")

        assert resp.status_code == 200
        assert [row["id"] for row in resp.data] == [str(mine.id)]
        assert resp.data[0]["reward_name"] == reward.name


class TestLoyaltyDashboard:
    def test_includes_next_reward_and_expiry(self, user, client_for, loyalty_settings):
        UserLoyaltyFactory(
            user=user, balance_points=150, last_activity_at=timezone.now()
        )
        RewardFactory(points_cost=100)
        goal = RewardFactory(points_cost=400)

        resp = client_for(user).get("/api/my/loyalty/")

        assert resp.status_code == 200
        assert resp.data["next_reward"]["id"] == str(goal.id)
        assert resp.data["points_to_next_reward"] == 250
        assert resp.data["points_expire_at"] is not None


class TestCacheInvalidation:
    def test_reward_changes_bump_the_catalog_cache(self):
        with mock.patch("navi_backend.awards.signals.bump_version") as bump:
            reward = RewardFactory()
            reward.archive()

        bump.assert_called_with(REWARDS_CACHE_NAMESPACE)
        assert bump.call_count >= 2

    def test_promotion_changes_bump_the_promotions_cache(self):
        with mock.patch("navi_backend.awards.signals.bump_version") as bump:
            PromotionFactory()

        bump.assert_called_with(PROMOTIONS_CACHE_NAMESPACE)
