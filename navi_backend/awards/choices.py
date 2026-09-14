"""Choice enums for the awards app.

Kept free of model imports so ``managers.py`` and other apps (e.g. ``orders``)
can use them without import cycles. ``models.py`` re-exports ``PointsReason``
so existing ``from navi_backend.awards.models import PointsReason`` imports keep
working.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class PointsReason(models.TextChoices):
    ORDER = "order", _("Order completed")
    AWARD_BONUS = "award_bonus", _("Award bonus")
    ADJUSTMENT = "adjustment", _("Manual adjustment")
    PROMOTION_BONUS = "promotion_bonus", _("Promotion bonus")
    REDEMPTION = "redemption", _("Reward redeemed")
    REDEMPTION_REVERSAL = "redemption_reversal", _("Reward redemption reversed")
    EXPIRY = "expiry", _("Points expired")


class PromotionScope(models.TextChoices):
    """What a :class:`Promotion` is attached to."""

    MENU_ITEM = "menu_item", _("Menu item")
    CATEGORY = "category", _("Category")
    CUSTOMIZATION = "customization", _("Customization")
    ORDER = "order", _("Whole order")


class PromotionEffect(models.TextChoices):
    """How a :class:`Promotion` changes the points earned."""

    MULTIPLIER = "multiplier", _("Points multiplier")
    FIXED = "fixed", _("Fixed bonus points")


class RedemptionStatus(models.TextChoices):
    APPLIED = "applied", _("Applied")
    REVERSED = "reversed", _("Reversed")
