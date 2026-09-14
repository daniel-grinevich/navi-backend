from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from navi_backend.awards.choices import PointsReason
from navi_backend.awards.choices import PromotionEffect
from navi_backend.awards.choices import PromotionScope
from navi_backend.awards.choices import RedemptionStatus
from navi_backend.awards.managers import PromotionQuerySet
from navi_backend.awards.managers import RewardQuerySet
from navi_backend.awards.managers import RewardRedemptionQuerySet
from navi_backend.awards.managers import UserLoyaltyQuerySet
from navi_backend.core.models import AuditModel
from navi_backend.core.models import NamedModel
from navi_backend.core.models import SlugifiedModel
from navi_backend.core.models import UUIDModel
from navi_backend.users.models import User

__all__ = [
    "Award",
    "AwardLevel",
    "LoyaltySettings",
    "PointsReason",
    "PointsTransaction",
    "Promotion",
    "PromotionEffect",
    "PromotionScope",
    "RedemptionStatus",
    "Reward",
    "RewardRedemption",
    "RuleType",
    "Tier",
    "UserAward",
    "UserLoyalty",
]

# Cache keys for rarely-changing loyalty reference data. See awards.signals for
# the Award invalidation hook; LoyaltySettings self-invalidates on save().
LOYALTY_SETTINGS_CACHE_KEY = "awards:loyalty_settings"
ACHIEVEMENTS_LIST_CACHE_KEY = "awards:achievements:list"
LOYALTY_SETTINGS_CACHE_TTL = 60 * 60  # 1 hour

# Namespaces for the customer-facing live rewards/promotions lists. Bumped from
# awards.signals whenever a Reward/Promotion changes (see core.cache).
REWARDS_CACHE_NAMESPACE = "awards:rewards"
PROMOTIONS_CACHE_NAMESPACE = "awards:promotions"


class RuleType(models.TextChoices):
    """The metric an :class:`Award` is measured against."""

    TOTAL_POINTS = "total_points", _("Total points earned")
    ORDERS_COMPLETED = "orders_completed", _("Orders completed")
    TOTAL_SPENT = "total_spent", _("Total amount spent")
    DISTINCT_ITEMS = "distinct_items", _("Distinct menu items tried")
    CUSTOMIZATIONS = "customizations", _("Customizations applied")


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
    points_expiry_days = models.PositiveIntegerField(
        _("points expiry (days)"),
        default=180,
        help_text=_(
            "Spendable points expire after this many days without any points "
            "activity. 0 means points never expire."
        ),
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
        # This singleton is read on every order completion and loyalty request;
        # drop the cache so the next read reflects the new config immediately.
        cache.delete(LOYALTY_SETTINGS_CACHE_KEY)

    @classmethod
    def load(cls):
        cached = cache.get(LOYALTY_SETTINGS_CACHE_KEY)
        if cached is not None:
            return cached
        obj, _created = cls.objects.get_or_create(pk=1)
        cache.set(LOYALTY_SETTINGS_CACHE_KEY, obj, LOYALTY_SETTINGS_CACHE_TTL)
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
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Value of the metric required to earn this award. Leave blank "
            "for a multi-level badge and define levels instead."
        ),
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

    def ordered_levels(self):
        """Levels by ascending rank. Cheap when ``levels`` is prefetched."""
        return sorted(self.levels.all(), key=lambda level: level.rank)


class AwardLevel(UUIDModel):
    """One tier of a multi-level award (e.g. Bronze/Silver/Gold).

    An award with levels is earned progressively: the user unlocks the highest
    level whose ``threshold`` their metric has crossed. Awards without levels
    fall back to the flat ``Award.threshold``.
    """

    award = models.ForeignKey(
        Award,
        on_delete=models.CASCADE,
        related_name="levels",
    )
    rank = models.PositiveIntegerField(
        _("rank"),
        help_text=_("1 is the first level; higher rank means a better level."),
    )
    name = models.CharField(
        _("name"),
        max_length=100,
        help_text=_('Level name shown to the user, e.g. "Bronze".'),
    )
    threshold = models.PositiveIntegerField(
        _("threshold"),
        validators=[MinValueValidator(1)],
        help_text=_("Value of the award's metric required to reach this level."),
    )
    points_reward = models.PositiveIntegerField(
        _("points reward"),
        default=0,
        help_text=_("Bonus points granted when this level is reached."),
    )
    icon = models.CharField(
        _("icon"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Icon name or URL for the frontend."),
    )

    class Meta:
        ordering = ["award", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["award", "rank"],
                name="unique_award_level_rank",
            ),
        ]

    def __str__(self):
        return f"{self.award} — {self.name} (rank {self.rank})"


class UserLoyalty(UUIDModel):
    """Per-user loyalty state: point balances, denormalized counters, tier and
    the user's own notification preference.

    ``balance_points`` is a PositiveIntegerField, so Postgres enforces
    ``balance_points >= 0`` with a CHECK constraint: a redemption or adjustment
    that would overdraw fails at the database, not just in Python.
    """

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
    last_activity_at = models.DateTimeField(
        _("last points activity"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Last time points were earned or spent. Drives expiry."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserLoyaltyQuerySet.as_manager()

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
    promotion = models.ForeignKey(
        "Promotion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points_transactions",
    )
    redemption = models.ForeignKey(
        "RewardRedemption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points_transactions",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points_transactions_created",
        help_text=_("Staff member behind a manual adjustment or reversal."),
    )
    balance_after = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Idempotency backstops for retried Celery tasks: one base grant per
            # order, one bonus per (order, promotion), one debit/refund per
            # redemption.
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(reason=PointsReason.ORDER),
                name="unique_order_points_per_order",
            ),
            models.UniqueConstraint(
                fields=["order", "promotion"],
                condition=Q(reason=PointsReason.PROMOTION_BONUS),
                name="unique_promotion_bonus_per_order",
            ),
            models.UniqueConstraint(
                fields=["redemption"],
                condition=Q(reason=PointsReason.REDEMPTION),
                name="unique_debit_per_redemption",
            ),
            models.UniqueConstraint(
                fields=["redemption"],
                condition=Q(reason=PointsReason.REDEMPTION_REVERSAL),
                name="unique_reversal_per_redemption",
            ),
        ]

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
    level = models.ForeignKey(
        AwardLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="earned_by",
        help_text=_("Highest level reached; empty for single-threshold awards."),
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


# ---------------------------------------------------------------------------
# Rewards: scheduled promotions, the redeemable catalog and redemptions
# ---------------------------------------------------------------------------


class ScheduleFields(models.Model):
    """When a Promotion or Reward is on offer.

    Every field is optional; leave them all blank for "always on" (still gated
    by ``status``/``is_deleted``). Days and times use the project ``TIME_ZONE``.
    """

    starts_at = models.DateTimeField(
        _("starts at"),
        null=True,
        blank=True,
        help_text=_("Not available before this moment. Blank = no start date."),
    )
    ends_at = models.DateTimeField(
        _("ends at"),
        null=True,
        blank=True,
        help_text=_("Not available from this moment on. Blank = no end date."),
    )
    days_of_week = ArrayField(
        models.PositiveSmallIntegerField(
            validators=[MinValueValidator(1), MaxValueValidator(7)],
        ),
        default=list,
        blank=True,
        help_text=_(
            "ISO weekdays it runs on (1 = Monday … 7 = Sunday). Blank = every day."
        ),
    )
    start_time = models.TimeField(
        _("daily start time"),
        null=True,
        blank=True,
        help_text=_("Available from this time each day. Blank = from midnight."),
    )
    end_time = models.TimeField(
        _("daily end time"),
        null=True,
        blank=True,
        help_text=_("Available until this time each day. Blank = until midnight."),
    )

    class Meta:
        abstract = True

    def schedule_errors(self):
        errors = {}
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = _("End must be after the start.")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = _("Daily end time must be after the daily start time.")
        if any(day not in range(1, 8) for day in self.days_of_week or []):
            errors["days_of_week"] = _(
                "Days must be ISO weekdays from 1 (Mon) to 7 (Sun)."
            )
        return errors


def _schedule_constraints(prefix):
    return [
        models.CheckConstraint(
            condition=Q(starts_at__isnull=True)
            | Q(ends_at__isnull=True)
            | Q(ends_at__gt=F("starts_at")),
            name=f"{prefix}_ends_after_starts",
        ),
        models.CheckConstraint(
            condition=Q(start_time__isnull=True)
            | Q(end_time__isnull=True)
            | Q(end_time__gt=F("start_time")),
            name=f"{prefix}_end_time_after_start_time",
        ),
    ]


def _raise_if_errors(errors):
    if errors:
        raise ValidationError(errors)


_ONLY_MENU_ITEM = Q(
    menu_item__isnull=False, category__isnull=True, customization__isnull=True
)
_ONLY_CATEGORY = Q(
    menu_item__isnull=True, category__isnull=False, customization__isnull=True
)
_ONLY_CUSTOMIZATION = Q(
    menu_item__isnull=True, category__isnull=True, customization__isnull=False
)
_NO_TARGET = Q(
    menu_item__isnull=True, category__isnull=True, customization__isnull=True
)
_TARGET_ID_FIELDS = ("menu_item_id", "category_id", "customization_id")
_SCOPE_TARGET_FIELDS: dict[str, str] = {
    PromotionScope.MENU_ITEM: "menu_item_id",
    PromotionScope.CATEGORY: "category_id",
    PromotionScope.CUSTOMIZATION: "customization_id",
}


class Promotion(UUIDModel, NamedModel, SlugifiedModel, AuditModel, ScheduleFields):
    """A scheduled bonus-points deal, e.g. "2x points on lattes, Tue 2-5pm".

    ``scope`` picks what it attaches to (a menu item, a category, a
    customization, or the whole order) and ``effect`` picks how it boosts
    points (a multiplier on the points already earned, or a fixed bonus).
    """

    description = models.TextField(_("description"), blank=True, default="")
    scope = models.CharField(
        _("scope"),
        max_length=16,
        choices=PromotionScope.choices,
        db_index=True,
    )
    effect = models.CharField(
        _("effect"), max_length=16, choices=PromotionEffect.choices
    )
    multiplier = models.DecimalField(
        _("multiplier"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("1.01"))],
        help_text=_("For multiplier promotions, e.g. 2.00 for double points."),
    )
    bonus_points = models.PositiveIntegerField(
        _("bonus points"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Fixed promotions: points per qualifying unit (or once per order)."
        ),
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotions",
    )
    category = models.ForeignKey(
        "menu.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotions",
    )
    customization = models.ForeignKey(
        "menu.Customization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="promotions",
    )
    min_order_total = models.DecimalField(
        _("minimum order total"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Order-scope only: the paid total must be at least this much."),
    )
    first_order_only = models.BooleanField(
        _("first order only"),
        default=False,
        help_text=_(
            "Order-scope only: applies to the customer's first completed order."
        ),
    )

    objects = PromotionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            *_schedule_constraints("promotion"),
            models.CheckConstraint(
                condition=Q(scope=PromotionScope.MENU_ITEM) & _ONLY_MENU_ITEM
                | Q(scope=PromotionScope.CATEGORY) & _ONLY_CATEGORY
                | Q(scope=PromotionScope.CUSTOMIZATION) & _ONLY_CUSTOMIZATION
                | Q(scope=PromotionScope.ORDER) & _NO_TARGET,
                name="promotion_scope_matches_target",
            ),
            models.CheckConstraint(
                condition=Q(
                    effect=PromotionEffect.MULTIPLIER,
                    multiplier__gt=1,
                    bonus_points__isnull=True,
                )
                | Q(
                    effect=PromotionEffect.FIXED,
                    bonus_points__gte=1,
                    multiplier__isnull=True,
                ),
                name="promotion_effect_matches_value",
            ),
            models.CheckConstraint(
                condition=Q(scope=PromotionScope.ORDER)
                | Q(min_order_total__isnull=True, first_order_only=False),
                name="promotion_order_options_need_order_scope",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = self.schedule_errors()
        errors.update(self._target_errors())
        errors.update(self._effect_errors())
        _raise_if_errors(errors)

    def _target_errors(self):
        expected = _SCOPE_TARGET_FIELDS.get(self.scope)
        chosen = {field for field in _TARGET_ID_FIELDS if getattr(self, field)}
        errors = {}
        if expected and chosen != {expected}:
            field = expected.removesuffix("_id")
            errors[field] = _("Choose exactly this target for the selected scope.")
        if self.scope == PromotionScope.ORDER and chosen:
            errors["scope"] = _("Order-wide promotions can't target an item.")
        if self.scope != PromotionScope.ORDER and (
            self.min_order_total is not None or self.first_order_only
        ):
            errors["scope"] = _(
                "Minimum order total and first-order-only need the order scope."
            )
        return errors

    def _effect_errors(self):
        if self.effect == PromotionEffect.MULTIPLIER:
            if self.multiplier is None or self.multiplier <= 1:
                return {"multiplier": _("A multiplier must be greater than 1.")}
            if self.bonus_points is not None:
                return {"bonus_points": _("Leave bonus points blank for a multiplier.")}
        if self.effect == PromotionEffect.FIXED:
            if not self.bonus_points:
                return {"bonus_points": _("Fixed promotions need bonus points.")}
            if self.multiplier is not None:
                return {
                    "multiplier": _("Leave the multiplier blank for fixed bonuses.")
                }
        return {}

    def matches_order_item(self, order_item):
        """Whether this item/category/customization promotion covers the line."""
        if self.scope == PromotionScope.MENU_ITEM:
            return order_item.menu_item_id == self.menu_item_id
        if self.scope == PromotionScope.CATEGORY:
            menu_item = order_item.menu_item
            return menu_item is not None and menu_item.category_id == self.category_id
        if self.scope == PromotionScope.CUSTOMIZATION:
            return any(
                oc.customization_id == self.customization_id
                for oc in order_item.customizations.all()
            )
        return False


class Reward(UUIDModel, NamedModel, SlugifiedModel, AuditModel, ScheduleFields):
    """A catalog entry customers redeem points for, e.g. "Free drink, 200 pts".

    Exactly one target: a specific menu item, any item in a category, or a
    customization (an "extra"). One redemption covers one unit, up to
    ``max_value``; the customer pays anything above that.
    """

    description = models.TextField(_("description"), blank=True, default="")
    icon = models.CharField(
        _("icon"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Icon name or URL for the frontend."),
    )
    points_cost = models.PositiveIntegerField(
        _("points cost"),
        validators=[MinValueValidator(1)],
    )
    max_value = models.DecimalField(
        _("maximum value"),
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_(
            "The most this reward can take off one unit, in dollars. The "
            "customer pays the difference on pricier items."
        ),
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rewards",
    )
    category = models.ForeignKey(
        "menu.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rewards",
    )
    customization = models.ForeignKey(
        "menu.Customization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rewards",
    )

    objects = RewardQuerySet.as_manager()

    class Meta:
        ordering = ["points_cost", "name"]
        constraints = [
            *_schedule_constraints("reward"),
            models.CheckConstraint(
                condition=_ONLY_MENU_ITEM | _ONLY_CATEGORY | _ONLY_CUSTOMIZATION,
                name="reward_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=Q(max_value__gt=0),
                name="reward_max_value_positive",
            ),
            models.CheckConstraint(
                condition=Q(points_cost__gte=1),
                name="reward_points_cost_positive",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.points_cost} pts)"

    def clean(self):
        super().clean()
        errors = self.schedule_errors()
        chosen = [field for field in _TARGET_ID_FIELDS if getattr(self, field)]
        if len(chosen) != 1:
            errors["menu_item"] = _(
                "Choose exactly one target: a menu item, a category or a customization."
            )
        if self.max_value is not None and self.max_value <= 0:
            errors["max_value"] = _("Maximum value must be greater than $0.00.")
        _raise_if_errors(errors)

    @property
    def target_type(self):
        for field in _TARGET_ID_FIELDS:
            if getattr(self, field):
                return field.removesuffix("_id")
        return None

    @property
    def target(self):
        return self.menu_item or self.category or self.customization

    @property
    def target_price(self):
        """Current menu price of the target, or None for a category."""
        if self.menu_item is not None:
            return self.menu_item.price
        if self.customization is not None:
            return self.customization.price
        return None

    def matches_order_item(self, order_item):
        if self.menu_item_id:
            return order_item.menu_item_id == self.menu_item_id
        if self.category_id:
            menu_item = order_item.menu_item
            return menu_item is not None and menu_item.category_id == self.category_id
        return False

    def matches_order_customization(self, order_customization):
        return bool(self.customization_id) and (
            order_customization.customization_id == self.customization_id
        )

    def discount_for(self, unit_price):
        """One unit, capped at ``max_value`` and never more than the unit costs."""
        return min(max(unit_price, Decimal("0.00")), self.max_value)


class RewardRedemption(UUIDModel):
    """A reward applied to one order line at checkout.

    ``discount_amount`` is snapshotted so later menu or reward edits never
    change what an order cost. Reversing a redemption (order cancelled, or an
    admin refund) returns the points but leaves the order's discount intact.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reward_redemptions",
    )
    reward = models.ForeignKey(
        Reward,
        on_delete=models.PROTECT,
        related_name="redemptions",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="reward_redemptions",
    )
    order_item = models.ForeignKey(
        "orders.OrderItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reward_redemptions",
    )
    order_customization = models.ForeignKey(
        "orders.OrderCustomization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reward_redemptions",
    )
    points_spent = models.PositiveIntegerField()
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(
        max_length=16,
        choices=RedemptionStatus.choices,
        default=RedemptionStatus.APPLIED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    objects = RewardRedemptionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(order_item__isnull=False, order_customization__isnull=True)
                | Q(order_item__isnull=True, order_customization__isnull=False),
                name="redemption_exactly_one_line",
            ),
            models.CheckConstraint(
                condition=Q(discount_amount__gte=0),
                name="redemption_discount_non_negative",
            ),
            models.UniqueConstraint(
                fields=["order_item"],
                name="unique_redemption_per_order_item",
            ),
            models.UniqueConstraint(
                fields=["order_customization"],
                name="unique_redemption_per_order_customization",
            ),
        ]

    def __str__(self):
        return f"{self.user} redeemed {self.reward} ({self.status})"
