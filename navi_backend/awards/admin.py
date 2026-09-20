from django.contrib import admin
from django.db.models import Count

from .models import Award
from .models import AwardLevel
from .models import LoyaltySettings
from .models import PointsTransaction
from .models import Tier
from .models import UserAward
from .models import UserLoyalty


@admin.register(LoyaltySettings)
class LoyaltySettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "points_per_dollar",
        "points_per_order",
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


@admin.register(UserLoyalty)
class UserLoyaltyAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "lifetime_points",
        "balance_points",
        "orders_completed",
        "total_spent",
        "current_tier",
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
    raw_id_fields = ("user", "order")
    readonly_fields = ("created_at",)


@admin.register(UserAward)
class UserAwardAdmin(admin.ModelAdmin):
    list_display = ("user", "award", "level", "earned_at")
    list_filter = ("award",)
    search_fields = ("user__email", "user__name", "award__name")
    raw_id_fields = ("user",)
    readonly_fields = ("earned_at",)
