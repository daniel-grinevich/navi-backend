from rest_framework import serializers

from navi_backend.awards.models import Award
from navi_backend.awards.models import AwardLevel
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.rules import metric_value
from navi_backend.core.api import BaseModelSerializer


class TierSerializer(BaseModelSerializer):
    show_only_to_admin_fields = ()

    class Meta:
        model = Tier
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "color",
            "threshold_points",
            "rank",
            "benefits",
        ]


class AwardLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AwardLevel
        fields = ["id", "rank", "name", "threshold", "points_reward", "icon"]


class AwardSerializer(BaseModelSerializer):
    rule_type_display = serializers.CharField(
        source="get_rule_type_display",
        read_only=True,
    )
    levels = AwardLevelSerializer(many=True, read_only=True)
    show_only_to_admin_fields = ()

    class Meta:
        model = Award
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "rule_type",
            "rule_type_display",
            "threshold",
            "points_reward",
            "levels",
        ]


class LoyaltySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltySettings
        fields = [
            "points_per_dollar",
            "points_per_order",
            "notifications_enabled",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class UserAwardSerializer(serializers.ModelSerializer):
    award = AwardSerializer(read_only=True)
    level = AwardLevelSerializer(read_only=True)

    class Meta:
        model = UserAward
        fields = ["id", "award", "level", "earned_at"]


class PointsTransactionSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(
        source="get_reason_display",
        read_only=True,
    )

    class Meta:
        model = PointsTransaction
        fields = [
            "id",
            "points",
            "reason",
            "reason_display",
            "order",
            "balance_after",
            "note",
            "created_at",
        ]


class AwardProgressSerializer(serializers.Serializer):
    """A single unearned award and how close the user is to earning it."""

    award = AwardSerializer()
    current = serializers.IntegerField()
    threshold = serializers.IntegerField()
    percent = serializers.IntegerField()


class LoyaltySummarySerializer(serializers.ModelSerializer):
    """The user-facing dashboard: balances, tier, next tier and progress."""

    current_tier = TierSerializer(read_only=True)
    next_tier = serializers.SerializerMethodField()
    points_to_next_tier = serializers.SerializerMethodField()
    earned_awards = serializers.SerializerMethodField()
    award_progress = serializers.SerializerMethodField()
    # Single source of truth for reward-email opt-in is the user's notification
    # preference; the dashboard reflects it (writes go through MyLoyaltyView).
    notifications_enabled = serializers.SerializerMethodField()

    class Meta:
        model = UserLoyalty
        fields = [
            "lifetime_points",
            "balance_points",
            "orders_completed",
            "total_spent",
            "current_tier",
            "next_tier",
            "points_to_next_tier",
            "notifications_enabled",
            "earned_awards",
            "award_progress",
        ]
        read_only_fields = [
            "lifetime_points",
            "balance_points",
            "orders_completed",
            "total_spent",
        ]

    def _next_tier(self, obj):
        # Resolved twice per instance (next_tier + points_to_next_tier); compute
        # the query once and reuse it.
        if not hasattr(self, "_next_tier_cache"):
            self._next_tier_cache = (
                Tier.objects.filter(
                    threshold_points__gt=obj.lifetime_points,
                    status=Tier.Status.ACTIVE,
                    is_deleted=False,
                )
                .order_by("threshold_points")
                .first()
            )
        return self._next_tier_cache

    def get_next_tier(self, obj):
        tier = self._next_tier(obj)
        return TierSerializer(tier).data if tier else None

    def get_points_to_next_tier(self, obj):
        tier = self._next_tier(obj)
        if not tier:
            return None
        return max(0, tier.threshold_points - obj.lifetime_points)

    def get_notifications_enabled(self, obj) -> bool:
        prefs = getattr(obj.user, "preferences", None)
        if prefs is None:
            return True
        return prefs.email_rewards

    def get_earned_awards(self, obj):
        qs = UserAward.objects.filter(user=obj.user).select_related("award")
        return UserAwardSerializer(qs, many=True).data

    def get_award_progress(self, obj):
        earned = {
            ua.award_id: ua
            for ua in UserAward.objects.filter(user=obj.user).select_related("level")
        }
        candidates = Award.objects.filter(
            status=Award.Status.ACTIVE, is_deleted=False
        ).prefetch_related("levels")

        progress = []
        for award in candidates:
            levels = award.ordered_levels()
            user_award = earned.get(award.id)
            if levels:
                # Leveled badges keep a next goal until the top level is hit.
                current_rank = (
                    user_award.level.rank if user_award and user_award.level else 0
                )
                next_level = next(
                    (level for level in levels if level.rank > current_rank),
                    None,
                )
                if next_level is None:
                    continue
                threshold = next_level.threshold
            else:
                if user_award is not None or not award.threshold:
                    continue
                threshold = award.threshold
            current = int(metric_value(award.rule_type, obj))
            percent = min(100, int(current * 100 / threshold)) if threshold else 0
            progress.append(
                {
                    "award": award,
                    "current": current,
                    "threshold": threshold,
                    "percent": percent,
                },
            )
        return AwardProgressSerializer(progress, many=True).data


# Maps backend award rule types to the metric strings the frontend achievements
# UI understands. Rule types without a dedicated frontend metric fall back to
# their raw value so nothing is silently hidden.
RULE_TO_METRIC = {
    RuleType.ORDERS_COMPLETED: "orders",
    RuleType.DISTINCT_ITEMS: "unique_drinks",
    RuleType.CUSTOMIZATIONS: "customizations",
    RuleType.TOTAL_POINTS: "points",
    RuleType.TOTAL_SPENT: "spent",
}


class AchievementSerializer(serializers.ModelSerializer):
    """An Award rendered in the shape the frontend badges UI expects.

    ``id`` is the stable slug (not the UUID) so the frontend can key on it.
    For multi-level badges ``target`` is the top level's threshold and
    ``levels`` lists every step so the UI can show the full ladder.
    """

    id = serializers.CharField(source="slug")
    label = serializers.CharField(source="name")
    desc = serializers.CharField(source="description")
    target = serializers.SerializerMethodField()
    metric = serializers.SerializerMethodField()
    levels = serializers.SerializerMethodField()

    class Meta:
        model = Award
        fields = ["id", "label", "desc", "target", "metric", "icon", "levels"]

    def get_metric(self, obj) -> str:
        return str(RULE_TO_METRIC.get(obj.rule_type, obj.rule_type))

    def get_target(self, obj) -> int:
        levels = obj.ordered_levels()
        if levels:
            return levels[-1].threshold
        return obj.threshold or 0

    def get_levels(self, obj) -> list:
        return [
            {
                "rank": level.rank,
                "name": level.name,
                "target": level.threshold,
                "icon": level.icon,
            }
            for level in obj.ordered_levels()
        ]


class AchievementProgressSerializer(serializers.Serializer):
    """Per-user progress toward a single badge (frontend contract).

    ``target`` is the user's *next* goal: the next level's threshold for
    multi-level badges, or the flat threshold otherwise. ``level`` is the
    name of the highest level reached (null when none / single-threshold).
    """

    id = serializers.CharField()
    current = serializers.IntegerField()
    target = serializers.IntegerField()
    unlocked = serializers.BooleanField()
    unlocked_at = serializers.DateTimeField(allow_null=True)
    level = serializers.CharField(allow_null=True)
    level_rank = serializers.IntegerField(allow_null=True)
    next_level = serializers.CharField(allow_null=True)
