from typing import Any

from django.contrib import admin
from django.db.models import Count
from django.db.models import Q

from navi_backend.core.cache import bump_version

from .models import PROMOTIONS_CACHE_NAMESPACE
from .models import REWARDS_CACHE_NAMESPACE
from .models import Award
from .models import AwardLevel
from .models import LoyaltySettings
from .models import PointsTransaction
from .models import Promotion
from .models import RedemptionStatus
from .models import Reward
from .models import RewardRedemption
from .models import Tier
from .models import UserAward
from .models import UserLoyalty

# Shared by PromotionAdmin and RewardAdmin. Typed Any: django-stubs only infers
# its fieldset TypedDict from literals written inline in the admin class.
SCHEDULE_FIELDSET: Any = (
    "Schedule",
    {
        "fields": ("starts_at", "ends_at", "days_of_week", "start_time", "end_time"),
        "description": (
            "All optional; leave blank for always on. Days are ISO weekdays "
            "(1 = Monday … 7 = Sunday). Times use the server time zone."
        ),
    },
)


def stamp_audit_users(request, obj, change):
    """AuditModel rows require created_by/updated_by, which admin forms hide."""
    if not change:
        obj.created_by = request.user
    obj.updated_by = request.user


def status_action(status, verb, cache_namespace):
    """Bulk status change that also clears the customer-facing cached list
    (``queryset.update`` skips the post_save signal that normally does it)."""

    @admin.action(description=f"{verb.capitalize()} selected")
    def change_status(modeladmin, request, queryset):
        updated = queryset.filter(is_deleted=False).update(status=status)
        bump_version(cache_namespace)
        modeladmin.message_user(request, f"{updated} row(s) {verb}d.")

    change_status.__name__ = f"{verb}_selected"
    return change_status


@admin.register(LoyaltySettings)
class LoyaltySettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "points_per_dollar",
        "points_per_order",
        "points_expiry_days",
        "notifications_enabled",
        "updated_at",
    )

    def has_add_permission(self, request):
        # Singleton: only ever one row.
        return not LoyaltySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ("name", "threshold_points", "rank", "status")
    list_filter = ("status",)
    search_fields = ("name",)
    ordering = ("threshold_points",)


class AwardLevelInline(admin.TabularInline):
    model = AwardLevel
    extra = 1
    fields = ("rank", "name", "threshold", "points_reward", "icon")
    ordering = ("rank",)


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    inlines = [AwardLevelInline]
    list_display = (
        "name",
        "rule_type",
        "threshold",
        "level_count",
        "points_reward",
        "earned_count",
        "status",
    )
    list_editable = ("status",)
    list_filter = ("rule_type", "status")
    search_fields = ("name", "slug")
    actions = ["activate_awards", "archive_awards"]
    fieldsets = (
        (
            None,
            {"fields": ("name", "slug", "description", "icon", "status")},
        ),
        (
            "Rule",
            {
                "fields": ("rule_type", "threshold", "points_reward"),
                "description": (
                    "The badge is earned when the user's metric reaches the "
                    "threshold. Threshold units follow the rule type: a count "
                    "for orders/items/customizations, dollars for total spent, "
                    "points for total points. For a multi-level badge (e.g. "
                    "Bronze/Silver/Gold) leave the threshold blank and define "
                    "levels below instead."
                ),
            },
        ),
    )
    prepopulated_fields = {"slug": ("name",)}

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(earned_count_agg=Count("earned_by", distinct=True))
            .prefetch_related("levels")
        )

    @admin.display(description="Earned by", ordering="earned_count_agg")
    def earned_count(self, obj):
        return obj.earned_count_agg

    @admin.display(description="Levels")
    def level_count(self, obj):
        return len(obj.levels.all()) or "—"

    @admin.action(description="Activate selected awards")
    def activate_awards(self, request, queryset):
        updated = queryset.update(status=Award.Status.ACTIVE)
        self.message_user(request, f"{updated} award(s) activated.")

    @admin.action(description="Archive selected awards")
    def archive_awards(self, request, queryset):
        updated = queryset.update(status=Award.Status.ARCHIVED)
        self.message_user(request, f"{updated} award(s) archived.")


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "scope",
        "effect",
        "multiplier",
        "bonus_points",
        "starts_at",
        "ends_at",
        "status",
        "times_applied",
    )
    list_filter = ("scope", "effect", "status", "is_deleted")
    search_fields = ("name", "slug", "description")
    raw_id_fields = ("menu_item", "category", "customization")
    prepopulated_fields = {"slug": ("name",)}
    actions = [
        status_action(Promotion.Status.ACTIVE, "activate", PROMOTIONS_CACHE_NAMESPACE),
        status_action(Promotion.Status.ARCHIVED, "archive", PROMOTIONS_CACHE_NAMESPACE),
    ]
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "status")}),
        (
            "Target",
            {
                "fields": ("scope", "menu_item", "category", "customization"),
                "description": (
                    "Pick the one target matching the scope. Whole-order "
                    "promotions have no target."
                ),
            },
        ),
        (
            "Effect",
            {
                "fields": (
                    "effect",
                    "multiplier",
                    "bonus_points",
                    "min_order_total",
                    "first_order_only",
                ),
                "description": (
                    "Multipliers (e.g. 2.00 = double points) don't stack; the "
                    "highest one wins per line. Fixed bonuses add up. Minimum "
                    "order total and first-order-only are for whole-order "
                    "promotions."
                ),
            },
        ),
        SCHEDULE_FIELDSET,
    )

    def get_queryset(self, request):
        return Promotion.objects.with_bonus_stats()

    @admin.display(description="Times applied", ordering="times_applied")
    def times_applied(self, obj):
        return obj.times_applied

    def save_model(self, request, obj, form, change):
        stamp_audit_users(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "points_cost",
        "max_value",
        "target_display",
        "starts_at",
        "ends_at",
        "status",
        "redemption_count",
    )
    list_filter = ("status", "is_deleted")
    search_fields = ("name", "slug", "description")
    raw_id_fields = ("menu_item", "category", "customization")
    prepopulated_fields = {"slug": ("name",)}
    actions = [
        status_action(Reward.Status.ACTIVE, "activate", REWARDS_CACHE_NAMESPACE),
        status_action(Reward.Status.ARCHIVED, "archive", REWARDS_CACHE_NAMESPACE),
    ]
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "icon", "status")}),
        (
            "Target",
            {
                "fields": ("menu_item", "category", "customization"),
                "description": (
                    "Choose exactly one: a specific menu item, any item in a "
                    "category, or a customization (an extra)."
                ),
            },
        ),
        (
            "Value",
            {
                "fields": ("points_cost", "max_value"),
                "description": (
                    "One redemption covers one unit, up to the maximum value. "
                    "Customers pay the difference on pricier items."
                ),
            },
        ),
        SCHEDULE_FIELDSET,
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("menu_item", "category", "customization")
            .annotate(
                redemption_count_agg=Count(
                    "redemptions",
                    filter=Q(redemptions__status=RedemptionStatus.APPLIED),
                )
            )
        )

    @admin.display(description="Target")
    def target_display(self, obj):
        target = obj.target
        return f"{obj.target_type}: {target}" if target else "—"

    @admin.display(description="Redemptions", ordering="redemption_count_agg")
    def redemption_count(self, obj):
        return obj.redemption_count_agg

    def save_model(self, request, obj, form, change):
        stamp_audit_users(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(RewardRedemption)
class RewardRedemptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "reward",
        "order",
        "points_spent",
        "discount_amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "reward")
    search_fields = ("user__email", "user__name", "reward__name")
    raw_id_fields = ("user", "reward", "order", "order_item", "order_customization")
    readonly_fields = ("created_at", "reversed_at")

    def has_add_permission(self, request):
        # Redemptions only come from checkout; refunds go through the API's
        # reverse action so the ledger stays consistent.
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserLoyalty)
class UserLoyaltyAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "lifetime_points",
        "balance_points",
        "orders_completed",
        "total_spent",
        "current_tier",
        "last_activity_at",
        "notifications_enabled",
    )
    search_fields = ("user__email", "user__name")
    list_filter = ("current_tier", "notifications_enabled")
    raw_id_fields = ("user", "current_tier")


@admin.register(PointsTransaction)
class PointsTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "points", "reason", "balance_after", "order", "created_at")
    list_filter = ("reason",)
    search_fields = ("user__email", "user__name")
    raw_id_fields = ("user", "order", "promotion", "redemption", "created_by")
    readonly_fields = ("created_at",)


@admin.register(UserAward)
class UserAwardAdmin(admin.ModelAdmin):
    list_display = ("user", "award", "level", "earned_at")
    list_filter = ("award",)
    search_fields = ("user__email", "user__name", "award__name")
    raw_id_fields = ("user",)
    readonly_fields = ("earned_at",)
