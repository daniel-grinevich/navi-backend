from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from navi_backend.core.models import AuditModel
from navi_backend.core.models import NamedModel
from navi_backend.core.models import SlugifiedModel
from navi_backend.core.models import UUIDModel
from navi_backend.users.models import User


class RuleType(models.TextChoices):
    """The metric an :class:`Award` is measured against."""

    TOTAL_POINTS = "total_points", _("Total points earned")
    ORDERS_COMPLETED = "orders_completed", _("Orders completed")
    TOTAL_SPENT = "total_spent", _("Total amount spent")
    DISTINCT_ITEMS = "distinct_items", _("Distinct menu items tried")


class PointsReason(models.TextChoices):
    ORDER = "order", _("Order completed")
    AWARD_BONUS = "award_bonus", _("Award bonus")
    ADJUSTMENT = "adjustment", _("Manual adjustment")


class LoyaltySettings(models.Model):
    """Singleton configuration for the loyalty/awards program.

    Editable via Django admin or the admin API so the earning rate and the
    global notification kill-switch can be tuned without a deploy.
    """

    points_per_dollar = models.DecimalField(
        _("points per dollar"),
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Points granted per dollar spent on a completed order."),
    )
    points_per_order = models.PositiveIntegerField(
        _("points per order"),
        default=0,
        help_text=_("Flat bonus points granted for each completed order."),
    )
    notifications_enabled = models.BooleanField(
        _("notifications enabled"),
        default=True,
        help_text=_(
            "Global kill-switch for award/tier notifications. When off, no "
            "notifications are sent regardless of a user's own preference."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Loyalty settings")
        verbose_name_plural = _("Loyalty settings")

    def __str__(self):
        return "Loyalty settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class Tier(UUIDModel, NamedModel, SlugifiedModel, AuditModel):
    """A loyalty tier reached once a user's lifetime points cross a threshold."""

    description = models.TextField(_("description"), blank=True, default="")
    icon = models.CharField(
        _("icon"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Icon name or URL for the frontend."),
    )
    color = models.CharField(
        _("color"),
        max_length=32,
        blank=True,
        default="",
        help_text=_("Hex value or design token for the frontend."),
    )
    threshold_points = models.PositiveIntegerField(
        _("threshold points"),
        default=0,
        db_index=True,
        help_text=_("Minimum lifetime points required to reach this tier."),
    )
    rank = models.PositiveIntegerField(
        _("rank"),
        default=0,
        help_text=_("Higher rank means a better tier. Used for ordering/upgrades."),
    )
    benefits = models.TextField(_("benefits"), blank=True, default="")

    class Meta:
        ordering = ["threshold_points", "rank"]

    def __str__(self):
        return f"{self.name} ({self.threshold_points}+ pts)"


class Award(UUIDModel, NamedModel, SlugifiedModel, AuditModel):
    """An achievement definition. Earned when a user's metric meets ``threshold``."""

    description = models.TextField(_("description"), blank=True, default="")
    icon = models.CharField(
        _("icon"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Icon name or URL for the frontend."),
    )
    rule_type = models.CharField(
        _("rule type"),
        max_length=32,
        choices=RuleType.choices,
        db_index=True,
        help_text=_("Which metric this award measures."),
    )
    threshold = models.PositiveIntegerField(
        _("threshold"),
        validators=[MinValueValidator(1)],
        help_text=_("Value of the metric required to earn this award."),
    )
    points_reward = models.PositiveIntegerField(
        _("points reward"),
        default=0,
        help_text=_("Bonus points granted when this award is earned."),
    )

    class Meta:
        ordering = ["rule_type", "threshold"]

    def __str__(self):
        return self.name


class UserLoyalty(UUIDModel):
    """Per-user loyalty state: point balances, denormalized counters, tier and
    the user's own notification preference."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="loyalty",
    )
    lifetime_points = models.PositiveIntegerField(
        _("lifetime points"),
        default=0,
        help_text=_("Total points ever earned. Drives tiers and awards."),
    )
    balance_points = models.PositiveIntegerField(
        _("balance points"),
        default=0,
        help_text=_("Currently spendable points."),
    )
    orders_completed = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(
        _("total spent"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    current_tier = models.ForeignKey(
        Tier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    notifications_enabled = models.BooleanField(
        _("notifications enabled"),
        default=True,
        help_text=_("User's own opt-in for award/tier notifications."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("User loyalty")
        verbose_name_plural = _("User loyalty")

    def __str__(self):
        return f"{self.user} — {self.lifetime_points} pts"

    @classmethod
    def for_user(cls, user):
        obj, _created = cls.objects.get_or_create(user=user)
        return obj


class PointsTransaction(UUIDModel):
    """Immutable ledger entry for every point movement."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="points_transactions",
    )
    points = models.IntegerField(
        help_text=_("Positive to grant, negative to deduct."),
    )
    reason = models.CharField(
        max_length=32,
        choices=PointsReason.choices,
        default=PointsReason.ORDER,
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points_transactions",
    )
    balance_after = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.points:+d} ({self.reason})"


class UserAward(UUIDModel):
    """Records that a user has earned a given award (once)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="awards",
    )
    award = models.ForeignKey(
        Award,
        on_delete=models.CASCADE,
        related_name="earned_by",
    )
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-earned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "award"],
                name="unique_user_award",
            ),
        ]

    def __str__(self):
        return f"{self.user} earned {self.award}"
