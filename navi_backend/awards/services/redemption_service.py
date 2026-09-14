"""Redeem rewards at checkout, and give the points back when an order is cancelled."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from navi_backend.awards.choices import PointsReason
from navi_backend.awards.choices import RedemptionStatus
from navi_backend.awards.models import Reward
from navi_backend.awards.models import RewardRedemption
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.exceptions import InsufficientPointsError
from navi_backend.awards.services.exceptions import RedemptionError
from navi_backend.awards.services.points_service import record_points
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.payments.constants import STRIPE_MINIMUM_CHARGE


def apply_redemptions(order, user, requests, *, at=None):
    """Redeem rewards against lines of a freshly created ``order``.

    ``requests`` is a list of ``(reward, line)`` pairs where ``line`` is an
    :class:`OrderItem` or :class:`OrderCustomization` of ``order``. Each
    redemption covers one unit, capped at the reward's ``max_value``. If the
    rewards leave less than Stripe can charge, that leftover is waived and the
    order is free.

    Runs inside the order's transaction: any problem raises
    :class:`RedemptionError` and the caller rolls back the order together with
    every point deducted so far.
    """
    if not requests:
        return []
    if user is None or user.is_guest:
        msg = "Sign in to a full account to redeem rewards."
        raise RedemptionError(msg)
    _reject_duplicate_lines(requests)

    reward_ids = {reward.pk for reward, _ in requests}
    live_ids = set(
        Reward.objects.live(at).filter(pk__in=reward_ids).values_list("pk", flat=True)
    )
    loyalty = UserLoyalty.for_user(user)

    with transaction.atomic():
        redemptions = []
        for reward, line in requests:
            if reward.pk not in live_ids:
                msg = f'"{reward.name}" is not available right now.'
                raise RedemptionError(msg)
            redemptions.append(_redeem_line(order, user, loyalty, reward, line))
        _waive_small_leftover(order, redemptions)
        _assert_total_not_negative(order)
    return redemptions


def _redeem_line(order, user, loyalty, reward, line):
    line_field, unit_price = _line_for(reward, line, order)
    discount = reward.discount_for(unit_price)
    if discount <= 0:
        msg = f'"{reward.name}" has nothing to take off this item.'
        raise RedemptionError(msg)

    redemption = RewardRedemption.objects.create(
        user=user,
        reward=reward,
        order=order,
        points_spent=reward.points_cost,
        discount_amount=discount,
        **line_field,
    )
    try:
        record_points(
            loyalty,
            -reward.points_cost,
            PointsReason.REDEMPTION,
            order=order,
            redemption=redemption,
            note=f"Redeemed: {reward.name}",
        )
    except InsufficientPointsError as exc:
        msg = (
            f'Not enough points for "{reward.name}": it costs '
            f"{reward.points_cost} and you have {loyalty.balance_points}."
        )
        raise RedemptionError(msg) from exc
    return redemption


def _line_for(reward, line, order):
    """Validate the reward fits the line; return its FK kwarg and unit price."""
    if isinstance(line, OrderItem):
        if line.order_id != order.pk or not reward.matches_order_item(line):
            msg = f'"{reward.name}" can\'t be used on this item.'
            raise RedemptionError(msg)
        return {"order_item": line}, line.unit_price

    if isinstance(line, OrderCustomization):
        belongs = line.order_item is not None and line.order_item.order_id == order.pk
        if not belongs or not reward.matches_order_customization(line):
            msg = f'"{reward.name}" can\'t be used on this customization.'
            raise RedemptionError(msg)
        return {"order_customization": line}, line.unit_price

    msg = "Rewards can only be applied to order items or customizations."
    raise RedemptionError(msg)


def _reject_duplicate_lines(requests):
    seen = set()
    for _, line in requests:
        key = (type(line).__name__, line.pk)
        if key in seen:
            msg = "Only one reward can be applied to each item or customization."
            raise RedemptionError(msg)
        seen.add(key)


def _assert_total_not_negative(order):
    # Backstop for the order floor: one capped redemption per line can't exceed
    # that line's price, but never let discounts outrun the subtotal.
    if order.discount_total > order.subtotal:
        msg = "Rewards can't take the order total below $0.00."
        raise RedemptionError(msg)


def _waive_small_leftover(order, redemptions):
    """Make the order free when rewards leave less than Stripe can charge.

    A $6.30 drink with a "free drink, up to $6" reward would leave $0.30, which
    Stripe won't charge. The last redemption absorbs the leftover so the stored
    discounts still add up to exactly what the order was reduced by.
    """
    leftover = order.subtotal - order.discount_total
    if not 0 < leftover < STRIPE_MINIMUM_CHARGE:
        return
    last = redemptions[-1]
    RewardRedemption.objects.filter(pk=last.pk).update(
        discount_amount=F("discount_amount") + leftover,
    )
    last.refresh_from_db(fields=["discount_amount"])


def reverse_redemption(redemption, *, created_by=None, note=""):
    """Give a redemption's points back. Returns False if already reversed.

    The order's discount is left untouched: the price was already authorized,
    so a reversal only refunds points. Lifetime points are not increased.
    """
    with transaction.atomic():
        # Compare-and-swap on status: the idempotency lock against a concurrent
        # cancel + admin reversal.
        updated = RewardRedemption.objects.filter(
            pk=redemption.pk,
            status=RedemptionStatus.APPLIED,
        ).update(status=RedemptionStatus.REVERSED, reversed_at=timezone.now())
        if not updated:
            return False

        loyalty, _ = UserLoyalty.objects.get_or_create(user_id=redemption.user_id)
        record_points(
            loyalty,
            redemption.points_spent,
            PointsReason.REDEMPTION_REVERSAL,
            order=redemption.order,
            redemption=redemption,
            note=note or f"Reversed: {redemption.reward.name}",
            created_by=created_by,
        )
    redemption.refresh_from_db(fields=["status", "reversed_at"])
    return True


def reverse_order_redemptions(order_ids, *, created_by=None):
    """Refund the points of every applied redemption on the given orders.

    Called when orders are cancelled. Idempotent. Returns how many redemptions
    were reversed.
    """
    redemptions = RewardRedemption.objects.filter(
        order_id__in=list(order_ids),
        status=RedemptionStatus.APPLIED,
    ).select_related("order", "reward")

    reversed_count = 0
    with transaction.atomic():
        for redemption in redemptions:
            note = f"Order cancelled: {redemption.reward.name}"
            if reverse_redemption(redemption, created_by=created_by, note=note):
                reversed_count += 1
    return reversed_count
