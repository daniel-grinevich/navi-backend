from rest_framework import serializers

from navi_backend.awards.models import Award
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsTransaction
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


class AwardSerializer(BaseModelSerializer):
    rule_type_display = serializers.CharField(
        source="get_rule_type_display",
        read_only=True,
    )
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

    class Meta:
        model = UserAward
        fields = ["id", "award", "earned_at"]


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
        return (
            Tier.objects.filter(
                threshold_points__gt=obj.lifetime_points,
                status=Tier.Status.ACTIVE,
                is_deleted=False,
            )
            .order_by("threshold_points")
            .first()
        )

    def get_next_tier(self, obj):
        tier = self._next_tier(obj)
        return TierSerializer(tier).data if tier else None

    def get_points_to_next_tier(self, obj):
        tier = self._next_tier(obj)
        if not tier:
            return None
        return max(0, tier.threshold_points - obj.lifetime_points)

    def get_earned_awards(self, obj):
        qs = UserAward.objects.filter(user=obj.user).select_related("award")
        return UserAwardSerializer(qs, many=True).data

    def get_award_progress(self, obj):
        earned_ids = set(
            UserAward.objects.filter(user=obj.user).values_list(
                "award_id",
                flat=True,
            ),
        )
        candidates = Award.objects.filter(
            status=Award.Status.ACTIVE, is_deleted=False
        ).exclude(id__in=earned_ids)

        progress = []
        for award in candidates:
            current = int(metric_value(award.rule_type, obj))
            if award.threshold:
                percent = min(100, int(current * 100 / award.threshold))
            else:
                percent = 0
            progress.append(
                {
                    "award": award,
                    "current": current,
                    "threshold": award.threshold,
                    "percent": percent,
                },
            )
        return AwardProgressSerializer(progress, many=True).data
