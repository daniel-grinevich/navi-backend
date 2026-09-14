"""Bonus points from scheduled promotions for a completed order.

Pure calculation: :func:`promotion_bonuses` says what each live promotion is
worth for an order and never writes. ``points_service.process_order`` records
the results as ``PROMOTION_BONUS`` ledger entries.
"""

from decimal import Decimal

from navi_backend.awards.choices import PromotionEffect
from navi_backend.awards.choices import PromotionScope
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import Promotion
from navi_backend.awards.models import RewardRedemption

ZERO = Decimal("0.00")


def promotion_bonuses(order, settings=None):
    """Return ``[(promotion, points), ...]`` for every live promotion that pays out.

    Promotions are evaluated at ``order.created_at``: a "2-5pm" deal counts when
    the customer ordered, not when the machine finished the drink.

    * A line's points come from what the customer actually paid for it (after
      reward discounts) x ``points_per_dollar``.
    * Multipliers never stack: each line gets the single highest multiplier
      among its item/category/customization promotions and any eligible
      order-wide one. The extra ``(multiplier - 1) x line points`` is credited
      to that promotion.
    * Fixed item/category/customization bonuses stack, per unit paid for.
    * Fixed order-wide bonuses are added once.
    """
    if order.user_id is None:
        return []

    promotions = list(Promotion.objects.live(order.created_at))
    if not promotions:
        return []

    rate = (settings or LoyaltySettings.load()).points_per_dollar
    order_wide = [
        promotion
        for promotion in promotions
        if promotion.scope == PromotionScope.ORDER
        and _order_promotion_applies(promotion, order)
    ]
    per_line = [p for p in promotions if p.scope != PromotionScope.ORDER]
    discounts = _discounts_by_line(order)

    totals: dict[object, tuple[Promotion, int]] = {}
    items = order.items.select_related("menu_item").prefetch_related("customizations")
    for item in items:
        _add_line_bonuses(item, per_line, order_wide, rate, discounts, totals)

    for promotion in order_wide:
        if promotion.effect == PromotionEffect.FIXED:
            _credit(totals, promotion, promotion.bonus_points)

    return [(promotion, points) for promotion, points in totals.values() if points > 0]


def _add_line_bonuses(item, per_line, order_wide, rate, discounts, totals):  # noqa: PLR0913
    item_discounts, customization_discounts = discounts
    customizations = list(item.customizations.all())
    line_discount = item_discounts.get(item.pk, ZERO) + sum(
        (customization_discounts.get(oc.pk, ZERO) for oc in customizations),
        ZERO,
    )
    paid = item.price - line_discount
    if paid <= 0:
        return

    matching = [
        promotion for promotion in per_line if promotion.matches_order_item(item)
    ]

    line_points = int(paid * rate)
    multipliers = [
        promotion
        for promotion in (*matching, *order_wide)
        if promotion.effect == PromotionEffect.MULTIPLIER
    ]
    if multipliers and line_points:
        best = max(multipliers, key=lambda promotion: promotion.multiplier)
        _credit(totals, best, int(line_points * (best.multiplier - 1)))

    for promotion in matching:
        if promotion.effect != PromotionEffect.FIXED:
            continue
        units = _paid_units(promotion, item, customizations, discounts)
        _credit(totals, promotion, promotion.bonus_points * units)


def _paid_units(promotion, item, customizations, discounts):
    """Units of the promoted thing the customer paid for (redeemed units excluded)."""
    item_discounts, customization_discounts = discounts
    if promotion.scope == PromotionScope.CUSTOMIZATION:
        return sum(
            max(0, oc.quantity - (1 if oc.pk in customization_discounts else 0))
            for oc in customizations
            if oc.customization_id == promotion.customization_id
        )
    return max(0, item.quantity - (1 if item.pk in item_discounts else 0))


def _discounts_by_line(order):
    item_discounts = {}
    customization_discounts = {}
    redemptions = RewardRedemption.objects.filter(order=order).only(
        "order_item_id",
        "order_customization_id",
        "discount_amount",
    )
    for redemption in redemptions:
        if redemption.order_item_id:
            item_discounts[redemption.order_item_id] = redemption.discount_amount
        else:
            customization_discounts[redemption.order_customization_id] = (
                redemption.discount_amount
            )
    return item_discounts, customization_discounts


def _order_promotion_applies(promotion, order):
    if (
        promotion.min_order_total is not None
        and order.price < promotion.min_order_total
    ):
        return False
    return not (promotion.first_order_only and _has_other_completed_order(order))


def _has_other_completed_order(order):
    # type(order) avoids importing orders.models into the awards services.
    return (
        type(order)
        .objects.filter(user_id=order.user_id, order_status="D")
        .exclude(pk=order.pk)
        .exists()
    )


def _credit(totals, promotion, points):
    if points <= 0:
        return
    _, current = totals.get(promotion.pk, (promotion, 0))
    totals[promotion.pk] = (promotion, current + points)
