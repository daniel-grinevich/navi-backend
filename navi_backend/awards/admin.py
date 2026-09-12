from django.contrib import admin

from .models import Award
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


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ("name", "rule_type", "threshold", "points_reward", "status")
    list_filter = ("rule_type", "status")
    search_fields = ("name",)


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
    list_display = ("user", "award", "earned_at")
    search_fields = ("user__email", "user__name", "award__name")
    raw_id_fields = ("user", "award")
    readonly_fields = ("earned_at",)
