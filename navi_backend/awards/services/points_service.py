"""Core loyalty engine.

``process_order`` is the single entry point invoked (asynchronously) when an
order is completed. It grants points, updates the user's denormalized counters,
evaluates awards and recomputes the tier — all in one transaction and
idempotent per order.
"""

import logging
from decimal import Decimal

from django.db import transaction

from navi_backend.awards.models import Award
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.rules import invalidate_user_metrics
from navi_backend.awards.services.rules import metric_value

logger = logging.getLogger(__name__)


def _record_points(loyalty, points, reason, order=None, note=""):
    """Apply a point movement and write an immutable ledger entry.

    Lifetime points only ever increase (they drive tiers/awards); the spendable
    balance can move in either direction but never goes below zero.
    """
    if points > 0:
        loyalty.lifetime_points += points
    loyalty.balance_points = max(0, loyalty.balance_points + points)
    loyalty.save(
        update_fields=["lifetime_points", "balance_points", "updated_at"],
    )
    return PointsTransaction.objects.create(
        user=loyalty.user,
        points=points,
        reason=reason,
        order=order,
        balance_after=loyalty.balance_points,
        note=note,
    )


def recompute_tier(loyalty):
    """Set the user's tier to the highest one their lifetime points qualify for.

    Returns the new :class:`Tier` if the user was upgraded, else ``None``.
    """
    tier = (
        Tier.objects.filter(
            threshold_points__lte=loyalty.lifetime_points,
            status=Tier.Status.ACTIVE,
            is_deleted=False,
        )
        .order_by("-threshold_points", "-rank")
        .first()
    )
    if tier is None or tier.id == loyalty.current_tier_id:
        return None

    loyalty.current_tier = tier
    loyalty.save(update_fields=["current_tier", "updated_at"])
    _notify_tier(loyalty, tier)
    return tier


def evaluate_awards(loyalty):
    """Grant any active awards the user now qualifies for but hasn't earned.

    Returns the list of newly earned :class:`Award` objects.
    """
    earned_ids = set(
        UserAward.objects.filter(user=loyalty.user).values_list(
            "award_id",
            flat=True,
        ),
    )
    candidates = Award.objects.filter(
        status=Award.Status.ACTIVE, is_deleted=False
    ).exclude(id__in=earned_ids)

    newly_earned = []
    for award in candidates:
        if metric_value(award.rule_type, loyalty) < award.threshold:
            continue
        _, created = UserAward.objects.get_or_create(user=loyalty.user, award=award)
        if not created:
            continue
        if award.points_reward:
            _record_points(
                loyalty,
                award.points_reward,
                PointsReason.AWARD_BONUS,
                note=f"Award: {award.name}",
            )
        _notify_award(loyalty, award)
        newly_earned.append(award)
    return newly_earned


@transaction.atomic
def process_order(order):
    """Grant points and evaluate awards/tiers for a completed order.

    Idempotent: if the order has already produced an ``ORDER`` ledger entry the
    call is a no-op. Guest/anonymous orders (no user) are skipped.
    """
    if order.user_id is None:
        return None

    already_processed = PointsTransaction.objects.filter(
        order=order,
        reason=PointsReason.ORDER,
    ).exists()
    if already_processed:
        logger.info("Order %s already processed for awards; skipping.", order.id)
        return None

    settings = LoyaltySettings.load()
    loyalty = UserLoyalty.for_user(order.user)

    order_total = order.price or Decimal("0.00")
    loyalty.orders_completed += 1
    loyalty.total_spent = (loyalty.total_spent or Decimal("0.00")) + order_total
    loyalty.save(update_fields=["orders_completed", "total_spent", "updated_at"])

    points = int(order_total * settings.points_per_dollar) + settings.points_per_order
    if points:
        _record_points(
            loyalty,
            points,
            PointsReason.ORDER,
            order=order,
            note="Order completed",
        )

    # This order changes the user's distinct-items / customizations tallies, so
    # drop their cached metric values before (re)evaluating awards.
    invalidate_user_metrics(order.user_id)

    newly_earned = evaluate_awards(loyalty)
    new_tier = recompute_tier(loyalty)

    return {
        "points_awarded": points,
        "awards": newly_earned,
        "tier": new_tier,
    }


def _should_notify(loyalty):
    """Both the global switch and the user's preference must be on."""
    global_on = LoyaltySettings.load().notifications_enabled
    return global_on and loyalty.notifications_enabled


def _notify_award(loyalty, award):
    if not _should_notify(loyalty):
        return
    # Lazy import: awards.tasks imports this module, so importing it at the top
    # would create a circular import.
    from navi_backend.awards.tasks import send_award_earned_email  # noqa: PLC0415

    send_award_earned_email.delay(str(loyalty.user_id), str(award.id))


def _notify_tier(loyalty, tier):
    if not _should_notify(loyalty):
        return
    from navi_backend.awards.tasks import send_tier_reached_email  # noqa: PLC0415

    send_tier_reached_email.delay(str(loyalty.user_id), str(tier.id))
