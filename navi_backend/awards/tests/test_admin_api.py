"""Staff-only rewards admin API (backs the admin frontend)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import RedemptionStatus
from navi_backend.awards.models import Reward
from navi_backend.awards.models import RewardRedemption
from navi_backend.awards.models import UserLoyalty
from navi_backend.menu.tests.factories import CategoryFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory
from navi_backend.users.tests.factories import UserFactory

from .factories import PromotionFactory
from .factories import RewardFactory
from .factories import UserLoyaltyFactory

pytestmark = pytest.mark.django_db

REWARDS_URL = "/api/admin/rewards/"
PROMOTIONS_URL = "/api/admin/promotions/"
REDEMPTIONS_URL = "/api/admin/redemptions/"
ACCOUNTS_URL = "/api/admin/loyalty-accounts/"
ADMIN_URLS = [REWARDS_URL, PROMOTIONS_URL, REDEMPTIONS_URL, ACCOUNTS_URL]


@pytest.fixture
def staff(db):
    return UserFactory(is_staff=True)


@pytest.fixture
def staff_client(staff):
    client = APIClient()
    client.force_authenticate(user=staff)
    return client


def _ids(response):
    return {row["id"] for row in response.data["results"]}


def _errors(response):
    # core.exceptions.custom_exception_handler wraps DRF errors in an envelope.
    return response.data["error"]["message"]


def _redemption(user, reward, *, status=RedemptionStatus.APPLIED, points=200):
    # navi_port=None: each NaviPort factory builds devices with a small pool of
    # unique names, which runs out when a test creates several orders.
    order = OrderFactory(user=user, order_status="O", payment=None, navi_port=None)
    item = OrderItemFactory(
        order=order,
        menu_item=reward.menu_item or MenuItemFactory(),
        unit_price=Decimal("5.00"),
    )
    return RewardRedemption.objects.create(
        user=user,
        reward=reward,
        order=order,
        order_item=item,
        points_spent=points,
        discount_amount=Decimal("5.00"),
        status=status,
    )


class TestPermissions:
    @pytest.mark.parametrize("url", ADMIN_URLS)
    def test_customers_are_forbidden(self, user, url):
        client = APIClient()
        client.force_authenticate(user=user)

        assert client.get(url).status_code == 403

    @pytest.mark.parametrize("url", ADMIN_URLS)
    def test_guests_are_forbidden(self, url):
        client = APIClient()
        client.force_authenticate(user=UserFactory(is_guest=True))

        assert client.get(url).status_code == 403

    @pytest.mark.parametrize("url", ADMIN_URLS)
    def test_anonymous_is_rejected(self, url):
        assert APIClient().get(url).status_code in (401, 403)

    def test_customers_cannot_create_rewards(self, user):
        client = APIClient()
        client.force_authenticate(user=user)

        resp = client.post(
            REWARDS_URL, {"name": "Free", "points_cost": 1}, format="json"
        )

        assert resp.status_code == 403


class TestAdminRewards:
    def test_create(self, staff_client, staff):
        latte = MenuItemFactory(price=Decimal("7.50"))

        resp = staff_client.post(
            REWARDS_URL,
            {
                "name": "Free latte",
                "points_cost": 200,
                "max_value": "6.00",
                "menu_item": str(latte.id),
            },
            format="json",
        )

        assert resp.status_code == 201, resp.data
        assert resp.data["is_live"] is True
        assert resp.data["target_type"] == "menu_item"
        assert resp.data["target_name"] == latte.name
        assert resp.data["max_value_below_price"] is True
        assert resp.data["redemption_count"] == 0
        reward = Reward.objects.get(pk=resp.data["id"])
        assert reward.slug == "free-latte"
        assert reward.created_by == staff

    @pytest.mark.parametrize(
        ("overrides", "error_field"),
        [
            ({"menu_item": "LATTE", "category": "CATEGORY"}, "menu_item"),
            ({}, "menu_item"),
            ({"menu_item": "LATTE", "max_value": "0.00"}, "max_value"),
            (
                {
                    "menu_item": "LATTE",
                    "starts_at": "2026-10-02T00:00:00Z",
                    "ends_at": "2026-10-01T00:00:00Z",
                },
                "ends_at",
            ),
            (
                {"menu_item": "LATTE", "start_time": "17:00", "end_time": "09:00"},
                "end_time",
            ),
            ({"menu_item": "LATTE", "days_of_week": [0, 8]}, "days_of_week"),
        ],
        ids=[
            "two-targets",
            "no-target",
            "zero-max-value",
            "ends-before-start",
            "daily-end-before-start",
            "bad-weekdays",
        ],
    )
    def test_validation(self, staff_client, overrides, error_field):
        placeholders = {
            "LATTE": str(MenuItemFactory().id),
            "CATEGORY": str(CategoryFactory().id),
        }
        payload = {"name": "Free thing", "points_cost": 100, "max_value": "6.00"}
        for key, value in overrides.items():
            is_placeholder = isinstance(value, str) and value in placeholders
            payload[key] = placeholders[value] if is_placeholder else value

        resp = staff_client.post(REWARDS_URL, payload, format="json")

        assert resp.status_code == 400
        assert error_field in _errors(resp)

    def test_partial_update_can_switch_target(self, staff_client, staff):
        reward = RewardFactory()
        category = CategoryFactory()

        resp = staff_client.patch(
            f"{REWARDS_URL}{reward.id}/",
            {"points_cost": 150, "menu_item": None, "category": str(category.id)},
            format="json",
        )

        assert resp.status_code == 200, resp.data
        assert resp.data["target_type"] == "category"
        assert resp.data["points_cost"] == 150
        assert resp.data["target_price"] is None
        reward.refresh_from_db()
        assert reward.updated_by == staff

    def test_destroy_soft_deletes_and_keeps_history(self, staff_client, user):
        reward = RewardFactory()
        redemption = _redemption(user, reward)

        resp = staff_client.delete(f"{REWARDS_URL}{reward.id}/")

        assert resp.status_code == 204
        reward.refresh_from_db()
        assert reward.is_deleted is True
        assert reward.status == Reward.Status.INACTIVE
        assert RewardRedemption.objects.filter(pk=redemption.pk).exists()
        assert str(reward.id) not in _ids(staff_client.get(REWARDS_URL))
        assert str(reward.id) in _ids(
            staff_client.get(REWARDS_URL, {"include_deleted": "true"})
        )

    def test_lifecycle_actions(self, staff_client):
        reward = RewardFactory()
        detail = f"{REWARDS_URL}{reward.id}"

        archived = staff_client.post(f"{detail}/archive/")
        assert archived.status_code == 200
        assert archived.data["status"] == Reward.Status.ARCHIVED
        assert archived.data["is_live"] is False

        staff_client.delete(f"{detail}/")
        assert staff_client.post(f"{detail}/activate/").status_code == 400

        restored = staff_client.post(f"{detail}/restore/")
        assert restored.status_code == 200
        assert restored.data["is_deleted"] is False

        activated = staff_client.post(f"{detail}/activate/")
        assert activated.status_code == 200
        assert activated.data["is_live"] is True

    def test_filters(self, staff_client):
        live = RewardFactory(name="Pumpkin special")
        archived = RewardFactory(status="R")
        upcoming = RewardFactory(starts_at=timezone.now() + timedelta(days=1))
        by_category = RewardFactory(menu_item=None, category=CategoryFactory())

        def ids(params):
            return _ids(staff_client.get(REWARDS_URL, params))

        assert ids({"is_live": "true"}) == {str(live.id), str(by_category.id)}
        assert ids({"is_live": "false"}) == {str(archived.id), str(upcoming.id)}
        assert ids({"status": "R"}) == {str(archived.id)}
        assert ids({"target_type": "category"}) == {str(by_category.id)}
        assert ids({"search": "pumpkin"}) == {str(live.id)}

    def test_stats_without_extra_queries_per_row(self, staff_client, user):
        reward = RewardFactory()
        _redemption(user, reward, points=200)
        _redemption(user, reward, points=200)
        _redemption(user, reward, status=RedemptionStatus.REVERSED, points=200)

        with CaptureQueriesContext(connection) as one_row:
            resp = staff_client.get(REWARDS_URL)

        row = resp.data["results"][0]
        assert row["redemption_count"] == 2
        assert row["points_redeemed"] == 400

        for extra in RewardFactory.create_batch(3):
            _redemption(user, extra)
        with CaptureQueriesContext(connection) as four_rows:
            resp = staff_client.get(REWARDS_URL)

        assert resp.data["count"] == 4
        assert len(four_rows) == len(one_row)


class TestAdminPromotions:
    def test_create_scheduled_order_wide_multiplier(self, staff_client):
        resp = staff_client.post(
            PROMOTIONS_URL,
            {
                "name": "Double points Tuesday",
                "scope": "order",
                "effect": "multiplier",
                "multiplier": "2.00",
                "days_of_week": [2],
                "start_time": "14:00",
                "end_time": "17:00",
            },
            format="json",
        )

        assert resp.status_code == 201, resp.data
        assert resp.data["scope"] == "order"
        assert resp.data["days_of_week"] == [2]
        assert resp.data["times_applied"] == 0

    @pytest.mark.parametrize(
        ("payload", "error_field"),
        [
            (
                {"scope": "menu_item", "effect": "multiplier", "multiplier": "2.00"},
                "menu_item",
            ),
            (
                {
                    "scope": "order",
                    "effect": "multiplier",
                    "multiplier": "2.00",
                    "bonus_points": 5,
                },
                "bonus_points",
            ),
            ({"scope": "order", "effect": "fixed"}, "bonus_points"),
            (
                {"scope": "order", "effect": "multiplier", "multiplier": "1.00"},
                "multiplier",
            ),
            (
                {
                    "scope": "category",
                    "category": "CATEGORY",
                    "effect": "fixed",
                    "bonus_points": 5,
                    "first_order_only": True,
                },
                "scope",
            ),
        ],
        ids=[
            "missing-target",
            "multiplier-with-bonus",
            "fixed-without-bonus",
            "multiplier-not-above-one",
            "order-option-on-category",
        ],
    )
    def test_validation(self, staff_client, payload, error_field):
        category_id = str(CategoryFactory().id)
        payload = {
            "name": "Bad promo",
            **{k: category_id if v == "CATEGORY" else v for k, v in payload.items()},
        }

        resp = staff_client.post(PROMOTIONS_URL, payload, format="json")

        assert resp.status_code == 400
        assert error_field in _errors(resp)

    def test_stats_come_from_the_ledger(self, staff_client, user):
        promotion = PromotionFactory()
        for points in (10, 15):
            PointsTransaction.objects.create(
                user=user,
                points=points,
                reason=PointsReason.PROMOTION_BONUS,
                order=OrderFactory(user=user, order_status="D", payment=None),
                promotion=promotion,
            )

        row = staff_client.get(PROMOTIONS_URL).data["results"][0]

        assert row["times_applied"] == 2
        assert row["bonus_points_granted"] == 25

    def test_scope_filter(self, staff_client):
        order_wide = PromotionFactory()
        PromotionFactory(scope="menu_item", menu_item=MenuItemFactory())

        assert _ids(staff_client.get(PROMOTIONS_URL, {"scope": "order"})) == {
            str(order_wide.id)
        }


class TestAdminRedemptions:
    def test_filters(self, staff_client, user):
        reward = RewardFactory()
        mine = _redemption(user, reward)
        other = _redemption(UserFactory(), reward, status=RedemptionStatus.REVERSED)

        assert _ids(staff_client.get(REDEMPTIONS_URL, {"user": user.pk})) == {
            str(mine.id)
        }
        assert _ids(staff_client.get(REDEMPTIONS_URL, {"status": "reversed"})) == {
            str(other.id)
        }
        assert (
            _ids(staff_client.get(REDEMPTIONS_URL, {"reward": "not-a-uuid"})) == set()
        )

    def test_reverse_refunds_points_once(self, staff_client, staff, user):
        UserLoyaltyFactory(user=user, balance_points=0)
        redemption = _redemption(user, RewardFactory(), points=200)
        url = f"{REDEMPTIONS_URL}{redemption.id}/reverse/"

        resp = staff_client.post(url)

        assert resp.status_code == 200
        assert resp.data["status"] == RedemptionStatus.REVERSED
        assert UserLoyalty.objects.get(user=user).balance_points == 200
        entry = PointsTransaction.objects.get(reason=PointsReason.REDEMPTION_REVERSAL)
        assert entry.created_by == staff

        assert staff_client.post(url).status_code == 400


class TestAdminLoyaltyAccounts:
    def test_search(self, staff_client):
        alice = UserLoyaltyFactory(
            user=UserFactory(email="alice@example.com"),
            balance_points=120,
            last_activity_at=timezone.now(),
        )
        UserLoyaltyFactory(user=UserFactory(email="bob@example.com"))

        resp = staff_client.get(ACCOUNTS_URL, {"search": "alice"})

        assert _ids(resp) == {str(alice.id)}
        row = resp.data["results"][0]
        assert row["user_email"] == "alice@example.com"
        assert row["points_expire_at"] is not None

    def test_transactions_are_the_users_ledger(self, staff_client, user):
        account = UserLoyaltyFactory(user=user)
        for points in (5, 7):
            PointsTransaction.objects.create(user=user, points=points)
        PointsTransaction.objects.create(user=UserFactory(), points=3)

        resp = staff_client.get(f"{ACCOUNTS_URL}{account.id}/transactions/")

        assert resp.status_code == 200
        assert resp.data["count"] == 2

    def test_adjust_credit(self, staff_client, staff, user):
        account = UserLoyaltyFactory(user=user, balance_points=10)

        resp = staff_client.post(
            f"{ACCOUNTS_URL}{account.id}/adjust/",
            {"points": 50, "note": "Drink was cold"},
            format="json",
        )

        assert resp.status_code == 201, resp.data
        assert resp.data["account"]["balance_points"] == 60
        assert resp.data["transaction"]["reason"] == PointsReason.ADJUSTMENT
        assert resp.data["transaction"]["created_by"] == staff.pk
        account.refresh_from_db()
        assert account.lifetime_points == 50

    def test_adjust_cannot_overdraw(self, staff_client, user):
        account = UserLoyaltyFactory(user=user, balance_points=10)

        resp = staff_client.post(
            f"{ACCOUNTS_URL}{account.id}/adjust/",
            {"points": -11, "note": "Oops"},
            format="json",
        )

        assert resp.status_code == 400
        account.refresh_from_db()
        assert account.balance_points == 10
        assert not PointsTransaction.objects.filter(
            reason=PointsReason.ADJUSTMENT
        ).exists()

    @pytest.mark.parametrize(
        "payload",
        [{"points": 0, "note": "zero"}, {"points": 5}, {"points": 5, "note": ""}],
        ids=["zero-points", "missing-note", "blank-note"],
    )
    def test_adjust_validation(self, staff_client, user, payload):
        account = UserLoyaltyFactory(user=user)

        resp = staff_client.post(
            f"{ACCOUNTS_URL}{account.id}/adjust/", payload, format="json"
        )

        assert resp.status_code == 400
