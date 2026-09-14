"""Core loyalty engine.

``process_order`` is the single entry point invoked (asynchronously) when an
order is completed. It grants points (base + scheduled promotion bonuses),
updates the user's denormalized counters, evaluates awards and recomputes the
tier — all in one transaction and idempotent per order.

``record_points`` is the only way a balance changes: earning, redeeming,
reversing, expiring and manual adjustments all go through it.
"""

import logging
from decimal import Decimal

from django.db import IntegrityError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from navi_backend.awards.models import Award
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsReason
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.exceptions import InsufficientPointsError
from navi_backend.awards.services.promotions import promotion_bonuses
from navi_backend.awards.services.rules import invalidate_user_metrics
from navi_backend.awards.services.rules import metric_value

logger = logging.getLogger(__name__)

_LOYALTY_POINT_FIELDS = [
    "balance_points",
    "lifetime_points",
    "last_activity_at",
    "updated_at",
]


def record_points(  # noqa: PLR0913
    loyalty,
    points,
    reason,
    *,
    order=None,
    promotion=None,
    redemption=None,
    note="",
    created_by=None,
    counts_toward_lifetime=None,
    touch_activity=True,
):
    """Apply a point movement and write an immutable ledger entry.

    The balance changes with a single ``UPDATE ... SET balance = balance + n``
    so concurrent grants and redemptions can't lose updates, and the database
    CHECK on ``balance_points`` rejects anything that would overdraw
    (raised here as :class:`InsufficientPointsError`).

    Lifetime points drive tiers/awards, so by default only genuine earning
    counts toward them: positive movements, except a reversal that merely
    hands back points already earned once.

    ``loyalty`` is refreshed in place so callers see the new balances.
    """
    if counts_toward_lifetime is None:
        counts_toward_lifetime = reason != PointsReason.REDEMPTION_REVERSAL

    now = timezone.now()
    updates = {"balance_points": F("balance_points") + points, "updated_at": now}
    if counts_toward_lifetime and points > 0:
        updates["lifetime_points"] = F("lifetime_points") + points
    if touch_activity:
        updates["last_activity_at"] = now

    with transaction.atomic():
        try:
            # Savepoint: a CHECK violation must not poison the caller's
            # transaction before we turn it into a domain error.
            with transaction.atomic():
                UserLoyalty.objects.filter(pk=loyalty.pk).update(**updates)
        except IntegrityError as exc:
            msg = f"Not enough points for a deduction of {-points}."
            raise InsufficientPointsError(msg) from exc

        loyalty.refresh_from_db(fields=_LOYALTY_POINT_FIELDS)
        return PointsTransaction.objects.create(
            user_id=loyalty.user_id,
            points=points,
            reason=reason,
            order=order,
            promotion=promotion,
            redemption=redemption,
            balance_after=loyalty.balance_points,
            note=note,
            created_by=created_by,
        )


def adjust_points(loyalty, points, *, note, staff_user):
    """Manual staff adjustment (support credit or correction).

    Positive adjustments count toward lifetime points, so awards and tier are
    re-evaluated once the adjustment commits.
    """
    with transaction.atomic():
        entry = record_points(
            loyalty,
            points,
            PointsReason.ADJUSTMENT,
            note=note,
            created_by=staff_user,
        )
        if points > 0:
            # Lazy import: awards.tasks imports this module.
            from navi_backend.awards.tasks import evaluate_user_awards  # noqa: PLC0415

            user_id = str(loyalty.user_id)
            transaction.on_commit(lambda: evaluate_user_awards.delay(user_id))
    return entry


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
    """Grant any active awards/levels the user now qualifies for.

    Single-threshold awards are earned once; multi-level awards upgrade the
    user's :class:`UserAward` to the highest level whose threshold the metric
    has crossed, granting the bonus points of every newly crossed level.

    Returns the list of :class:`Award` objects newly earned or leveled up.
    """
    existing = {
        ua.award_id: ua
        for ua in UserAward.objects.filter(user=loyalty.user).select_related("level")
    }
    candidates = Award.objects.filter(
        status=Award.Status.ACTIVE, is_deleted=False
    ).prefetch_related("levels")

    newly_earned = []
    for award in candidates:
        levels = award.ordered_levels()
        if levels:
            if _evaluate_leveled_award(loyalty, award, levels, existing.get(award.id)):
                newly_earned.append(award)
        elif _evaluate_flat_award(loyalty, award, existing.get(award.id)):
            newly_earned.append(award)
    return newly_earned


def _evaluate_flat_award(loyalty, award, user_award):
    """Earn a single-threshold award. Returns True if newly earned."""
    if user_award is not None or not award.threshold:
        return False
    if metric_value(award.rule_type, loyalty) < award.threshold:
        return False
    _, created = UserAward.objects.get_or_create(user=loyalty.user, award=award)
    if not created:
        return False
    if award.points_reward:
        record_points(
            loyalty,
            award.points_reward,
            PointsReason.AWARD_BONUS,
            note=f"Award: {award.name}",
        )
    _notify_award(loyalty, award)
    return True


def _evaluate_leveled_award(loyalty, award, levels, user_award):
    """Upgrade a multi-level award to the highest crossed level.

    Returns True if a new level was reached.
    """
    current_rank = user_award.level.rank if user_award and user_award.level else 0
    value = metric_value(award.rule_type, loyalty)
    crossed = [
        level
        for level in levels
        if level.rank > current_rank and value >= level.threshold
    ]
    if not crossed:
        return False
    top = crossed[-1]

    if user_award is None:
        user_award, created = UserAward.objects.get_or_create(
            user=loyalty.user,
            award=award,
            defaults={"level": top},
        )
        if not created:
            # Raced with a concurrent evaluation that already earned it.
            return False
    else:
        # Compare-and-swap on the previous level so a concurrent evaluation
        # can't double-grant the level bonus.
        updated = UserAward.objects.filter(
            pk=user_award.pk,
            level=user_award.level,
        ).update(level=top)
        if not updated:
            return False

    bonus = sum(level.points_reward for level in crossed)
    if bonus:
        record_points(
            loyalty,
            bonus,
            PointsReason.AWARD_BONUS,
            note=f"Award: {award.name} — {top.name}",
        )
    _notify_award(loyalty, award, level=top)
    return True


@transaction.atomic
def process_order(order):
    """Grant points and evaluate awards/tiers for a completed order.

    Idempotent: if the order has already produced an ``ORDER`` ledger entry the
    call is a no-op (a unique constraint backs this up against races).
    Orders without a user, or placed by a guest account, are skipped.
    """
    if order.user_id is None or order.user.is_guest:
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

    # What the customer actually paid: reward discounts never earn points.
    order_total = order.price or Decimal("0.00")
    UserLoyalty.objects.filter(pk=loyalty.pk).update(
        orders_completed=F("orders_completed") + 1,
        total_spent=F("total_spent") + order_total,
        updated_at=timezone.now(),
    )
    loyalty.refresh_from_db(fields=["orders_completed", "total_spent"])

    base_points = (
        int(order_total * settings.points_per_dollar) + settings.points_per_order
    )
    # Always write the ORDER entry, even for 0 points (e.g. a fully redeemed
    # order): it is the idempotency marker for this order.
    record_points(
        loyalty,
        base_points,
        PointsReason.ORDER,
        order=order,
        note="Order completed",
    )

    bonus_points = 0
    for promotion, points in promotion_bonuses(order, settings):
        record_points(
            loyalty,
            points,
            PointsReason.PROMOTION_BONUS,
            order=order,
            promotion=promotion,
            note=f"Promotion: {promotion.name}",
        )
        bonus_points += points

    # This order changes the user's distinct-items / customizations tallies, so
    # drop their cached metric values before (re)evaluating awards.
    invalidate_user_metrics(order.user_id)

    newly_earned = evaluate_awards(loyalty)
    new_tier = recompute_tier(loyalty)

    return {
        "points_awarded": base_points + bonus_points,
        "base_points": base_points,
        "bonus_points": bonus_points,
        "awards": newly_earned,
        "tier": new_tier,
    }


def _should_notify(loyalty):
    """Both the global switch and the user's preference must be on."""
    global_on = LoyaltySettings.load().notifications_enabled
    return global_on and loyalty.notifications_enabled


def _notify_award(loyalty, award, level=None):
    if not _should_notify(loyalty):
        return
    # Lazy import: awards.tasks imports this module, so importing it at the top
    # would create a circular import.
    from navi_backend.awards.tasks import send_award_earned_email  # noqa: PLC0415

    send_award_earned_email.delay(
        str(loyalty.user_id),
        str(award.id),
        str(level.id) if level else None,
    )


def _notify_tier(loyalty, tier):
    if not _should_notify(loyalty):
        return
    from navi_backend.awards.tasks import send_tier_reached_email  # noqa: PLC0415

    send_tier_reached_email.delay(str(loyalty.user_id), str(tier.id))
