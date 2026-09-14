"""Custom querysets for the awards app.

Reusable query logic (what is live right now, admin filters, stats) lives here
so views stay thin and the database does the filtering and aggregation.
"""

import uuid
from datetime import datetime
from datetime import time

from django.db import models
from django.db.models import Count
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.dateparse import parse_datetime

from navi_backend.awards.choices import PointsReason
from navi_backend.awards.choices import RedemptionStatus

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}


def _parse_bool(value):
    """Return True/False for a query-param flag, or None when absent/invalid."""
    if value is None:
        return None
    lowered = str(value).lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    return None


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def _parse_moment(value, *, end_of_day=False):
    """Parse an ISO datetime or date query param into an aware datetime."""
    if not value:
        return None
    moment = parse_datetime(value)
    if moment is None:
        day = parse_date(value)
        if day is None:
            return None
        moment = datetime.combine(day, time.max if end_of_day else time.min)
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return moment


class ScheduledQuerySet(models.QuerySet):
    """Shared by models with ``ScheduleFields`` + ``AuditModel`` status."""

    def live(self, at=None):
        """Rows on offer at ``at`` (default: now), evaluated entirely in SQL.

        Days of week and times of day are interpreted in the project's local
        ``TIME_ZONE`` (a "2-5pm Tuesday" deal means 2-5pm Tuesday in-store).
        """
        local = timezone.localtime(at or timezone.now())
        weekday = local.isoweekday()
        clock = local.time()
        return self.filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=local),
            Q(ends_at__isnull=True) | Q(ends_at__gt=local),
            Q(days_of_week=[]) | Q(days_of_week__contains=[weekday]),
            Q(start_time__isnull=True) | Q(start_time__lte=clock),
            Q(end_time__isnull=True) | Q(end_time__gt=clock),
            status=self.model.Status.ACTIVE,
            is_deleted=False,
        )

    def annotate_is_live(self, at=None):
        live = self.model.objects.live(at).filter(pk=OuterRef("pk"))
        return self.annotate(is_live=Exists(live))

    def admin_filter(self, params, at=None):
        """Apply the admin list filters shared by rewards and promotions."""
        qs = self.annotate_is_live(at)
        if not _parse_bool(params.get("include_deleted")):
            qs = qs.filter(is_deleted=False)
        if status := params.get("status"):
            qs = qs.filter(status=status)
        is_live = _parse_bool(params.get("is_live"))
        if is_live is not None:
            qs = qs.filter(is_live=is_live)
        if search := params.get("search"):
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return qs


class RewardQuerySet(ScheduledQuerySet):
    TARGET_FIELDS = ("menu_item", "category", "customization")

    def with_redemption_stats(self):
        applied = Q(redemptions__status=RedemptionStatus.APPLIED)
        return self.annotate(
            redemption_count=Count("redemptions", filter=applied),
            points_redeemed=Coalesce(
                Sum("redemptions__points_spent", filter=applied),
                0,
            ),
        )

    def admin_filter(self, params, at=None):
        qs = super().admin_filter(params, at)
        target_type = params.get("target_type")
        if target_type in self.TARGET_FIELDS:
            qs = qs.filter(**{f"{target_type}__isnull": False})
        return qs


class PromotionQuerySet(ScheduledQuerySet):
    def with_bonus_stats(self):
        bonus = Q(points_transactions__reason=PointsReason.PROMOTION_BONUS)
        return self.annotate(
            times_applied=Count("points_transactions", filter=bonus),
            bonus_points_granted=Coalesce(
                Sum("points_transactions__points", filter=bonus),
                0,
            ),
        )

    def admin_filter(self, params, at=None):
        qs = super().admin_filter(params, at)
        if scope := params.get("scope"):
            qs = qs.filter(scope=scope)
        if effect := params.get("effect"):
            qs = qs.filter(effect=effect)
        return qs


class UserLoyaltyQuerySet(models.QuerySet):
    def expirable(self, cutoff):
        """Accounts holding points whose last activity is older than ``cutoff``."""
        return self.filter(balance_points__gt=0, last_activity_at__lt=cutoff)

    def search(self, term):
        if not term:
            return self
        return self.filter(
            Q(user__email__icontains=term) | Q(user__name__icontains=term)
        )


class RewardRedemptionQuerySet(models.QuerySet):
    _ID_FILTERS = (("user", "user_id"), ("reward", "reward_id"), ("order", "order_id"))

    def admin_filter(self, params):
        qs = self
        for param, field in self._ID_FILTERS:
            value = params.get(param)
            if not value:
                continue
            if param != "user" and not _is_uuid(value):
                # A malformed id can't match anything; don't 500 on it.
                return self.none()
            qs = qs.filter(**{field: value})
        if status := params.get("status"):
            qs = qs.filter(status=status)
        if created_after := _parse_moment(params.get("created_after")):
            qs = qs.filter(created_at__gte=created_after)
        created_before = _parse_moment(params.get("created_before"), end_of_day=True)
        if created_before:
            qs = qs.filter(created_at__lte=created_before)
        return qs
