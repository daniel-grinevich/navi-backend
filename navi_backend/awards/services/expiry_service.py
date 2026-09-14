"""Expire spendable points after a period without any points activity."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from navi_backend.awards.choices import PointsReason
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.points_service import record_points


def points_expire_at(loyalty, settings=None):
    """When the user's current balance will expire, or None if it won't."""
    settings = settings or LoyaltySettings.load()
    days = settings.points_expiry_days
    if not days or not loyalty.balance_points or loyalty.last_activity_at is None:
        return None
    return loyalty.last_activity_at + timedelta(days=days)


def expire_inactive_points(now=None):
    """Zero the balance of every account inactive for ``points_expiry_days``.

    Each account expires in its own transaction under a row lock, re-checking
    inactivity so points earned or spent mid-run are never expired. Returns how
    many accounts were expired.
    """
    settings = LoyaltySettings.load()
    days = settings.points_expiry_days
    if not days:
        return 0

    cutoff = (now or timezone.now()) - timedelta(days=days)
    candidate_ids = list(
        UserLoyalty.objects.expirable(cutoff).values_list("pk", flat=True)
    )
    return sum(_expire_one(loyalty_id, cutoff, days) for loyalty_id in candidate_ids)


def _expire_one(loyalty_id, cutoff, days):
    with transaction.atomic():
        loyalty = (
            UserLoyalty.objects.select_for_update()
            .expirable(cutoff)
            .filter(pk=loyalty_id)
            .first()
        )
        if loyalty is None:
            return 0
        record_points(
            loyalty,
            -loyalty.balance_points,
            PointsReason.EXPIRY,
            note=f"Expired after {days} days without points activity",
            touch_activity=False,
        )
    return 1
