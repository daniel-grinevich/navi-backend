"""Points expire after ``points_expiry_days`` without any points activity."""

from datetime import timedelta

import pytest
from django.utils import timezone

from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.services.expiry_service import expire_inactive_points
from navi_backend.awards.services.expiry_service import points_expire_at
from navi_backend.awards.tasks import expire_inactive_points_task

from .factories import UserLoyaltyFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def now():
    return timezone.now()


@pytest.fixture
def expiry_settings(loyalty_settings):
    loyalty_settings.points_expiry_days = 30
    loyalty_settings.save()
    return loyalty_settings


def _account(now, days_idle, balance=100):
    return UserLoyaltyFactory(
        balance_points=balance,
        lifetime_points=balance,
        last_activity_at=now - timedelta(days=days_idle),
    )


class TestExpireInactivePoints:
    def test_expires_an_idle_balance(self, expiry_settings, now):
        account = _account(now, days_idle=31)
        last_activity = account.last_activity_at

        assert expire_inactive_points(now) == 1

        account.refresh_from_db()
        assert account.balance_points == 0
        assert account.lifetime_points == 100  # tiers/badges are unaffected
        assert account.last_activity_at == last_activity
        entry = PointsTransaction.objects.get(user=account.user)
        assert entry.reason == PointsReason.EXPIRY
        assert entry.points == -100
        assert entry.balance_after == 0

    def test_recent_activity_keeps_points(self, expiry_settings, now):
        account = _account(now, days_idle=29)

        assert expire_inactive_points(now) == 0
        account.refresh_from_db()
        assert account.balance_points == 100

    def test_exactly_at_the_cutoff_is_kept(self, expiry_settings, now):
        _account(now, days_idle=30)

        assert expire_inactive_points(now) == 0

    def test_zero_days_means_never(self, loyalty_settings, now):
        loyalty_settings.points_expiry_days = 0
        loyalty_settings.save()
        _account(now, days_idle=1000)

        assert expire_inactive_points(now) == 0

    def test_empty_and_never_active_accounts_are_skipped(self, expiry_settings, now):
        _account(now, days_idle=90, balance=0)
        UserLoyaltyFactory(balance_points=100, last_activity_at=None)

        assert expire_inactive_points(now) == 0
        assert not PointsTransaction.objects.exists()

    def test_daily_task_runs_the_expiry(self, expiry_settings, now):
        _account(now, days_idle=31)

        assert expire_inactive_points_task() == 1


class TestPointsExpireAt:
    def test_counts_from_last_activity(self, expiry_settings, now):
        account = _account(now, days_idle=10)

        assert points_expire_at(account) == account.last_activity_at + timedelta(
            days=30
        )

    def test_none_when_nothing_can_expire(self, loyalty_settings, now):
        empty = _account(now, days_idle=10, balance=0)
        assert points_expire_at(empty) is None

        loyalty_settings.points_expiry_days = 0
        loyalty_settings.save()
        assert points_expire_at(_account(now, days_idle=10)) is None
