import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from navi_backend.awards.models import Award
from navi_backend.awards.models import AwardLevel
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import Promotion
from navi_backend.awards.models import Reward
from navi_backend.awards.models import RewardRedemption
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.expiry_service import points_expire_at
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
            "points_expiry_days",
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


# ---------------------------------------------------------------------------
# Rewards, customer-facing
# ---------------------------------------------------------------------------

_SCHEDULE_FIELDS = ["starts_at", "ends_at", "days_of_week", "start_time", "end_time"]
_TARGET_FIELDS = ["menu_item", "category", "customization"]


def _target_name(obj):
    target = getattr(obj, "target", None) or (
        obj.menu_item or obj.category or obj.customization
    )
    return target.name if target else None


class RewardSerializer(serializers.ModelSerializer):
    """A live catalog entry. ``max_value`` lets the app show "up to $6"."""

    target_type = serializers.CharField(read_only=True)
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = Reward
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "points_cost",
            "max_value",
            "target_type",
            *_TARGET_FIELDS,
            "target_name",
            *_SCHEDULE_FIELDS,
        ]
        read_only_fields = fields

    def get_target_name(self, obj) -> str | None:
        return _target_name(obj)


class PromotionSerializer(serializers.ModelSerializer):
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = Promotion
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "scope",
            "effect",
            "multiplier",
            "bonus_points",
            *_TARGET_FIELDS,
            "target_name",
            "min_order_total",
            "first_order_only",
            *_SCHEDULE_FIELDS,
        ]
        read_only_fields = fields

    def get_target_name(self, obj) -> str | None:
        return _target_name(obj)


class RedemptionSerializer(serializers.ModelSerializer):
    reward_name = serializers.CharField(source="reward.name", read_only=True)

    class Meta:
        model = RewardRedemption
        fields = [
            "id",
            "reward",
            "reward_name",
            "order",
            "order_item",
            "order_customization",
            "points_spent",
            "discount_amount",
            "status",
            "created_at",
            "reversed_at",
        ]
        read_only_fields = fields


class LoyaltySummarySerializer(serializers.ModelSerializer):
    """The user-facing dashboard: balances, tier, next tier/reward and progress."""

    current_tier = TierSerializer(read_only=True)
    next_tier = serializers.SerializerMethodField()
    points_to_next_tier = serializers.SerializerMethodField()
    next_reward = serializers.SerializerMethodField()
    points_to_next_reward = serializers.SerializerMethodField()
    points_expire_at = serializers.SerializerMethodField()
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
            "next_reward",
            "points_to_next_reward",
            "points_expire_at",
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

    def _next_reward(self, obj):
        # The cheapest live reward the user can't afford yet: their next goal.
        if not hasattr(self, "_next_reward_cache"):
            self._next_reward_cache = (
                Reward.objects.live()
                .filter(points_cost__gt=obj.balance_points)
                .select_related(*_TARGET_FIELDS)
                .order_by("points_cost")
                .first()
            )
        return self._next_reward_cache

    def get_next_tier(self, obj):
        tier = self._next_tier(obj)
        return TierSerializer(tier).data if tier else None

    def get_points_to_next_tier(self, obj):
        tier = self._next_tier(obj)
        if not tier:
            return None
        return max(0, tier.threshold_points - obj.lifetime_points)

    def get_next_reward(self, obj):
        reward = self._next_reward(obj)
        return RewardSerializer(reward).data if reward else None

    def get_points_to_next_reward(self, obj) -> int | None:
        reward = self._next_reward(obj)
        if not reward:
            return None
        return reward.points_cost - obj.balance_points

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_points_expire_at(self, obj):
        return points_expire_at(obj)

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


# ---------------------------------------------------------------------------
# Rewards admin frontend (staff-only endpoints under /api/admin/)
# ---------------------------------------------------------------------------

_ADMIN_READ_ONLY = [
    "id",
    "slug",
    "is_deleted",
    "deleted_at",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
]


def validate_with_model_clean(serializer, attrs):
    """Run the model's ``clean()`` on the would-be instance.

    Keeps the API and Django admin on exactly the same rules (one target,
    positive max value, sane schedule, scope/effect pairs...).
    """
    model = serializer.Meta.model
    candidate = copy.copy(serializer.instance) if serializer.instance else model()
    for field, value in attrs.items():
        setattr(candidate, field, value)
    try:
        candidate.clean()
    except DjangoValidationError as exc:
        raise serializers.ValidationError(serializers.as_serializer_error(exc)) from exc
    return attrs


class AdminRewardSerializer(serializers.ModelSerializer):
    """Every field of a reward, plus live status and redemption stats."""

    target_type = serializers.CharField(read_only=True)
    target_name = serializers.SerializerMethodField()
    target_price = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        read_only=True,
    )
    max_value_below_price = serializers.SerializerMethodField(
        help_text="True when the target costs more than max_value, so customers "
        "pay the difference.",
    )
    is_live = serializers.BooleanField(read_only=True, default=False)
    redemption_count = serializers.IntegerField(read_only=True, default=0)
    points_redeemed = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Reward
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "points_cost",
            "max_value",
            *_TARGET_FIELDS,
            "target_type",
            "target_name",
            "target_price",
            "max_value_below_price",
            *_SCHEDULE_FIELDS,
            "status",
            "is_live",
            "is_deleted",
            "deleted_at",
            "redemption_count",
            "points_redeemed",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = _ADMIN_READ_ONLY

    def get_target_name(self, obj) -> str | None:
        return _target_name(obj)

    def get_max_value_below_price(self, obj) -> bool:
        price = obj.target_price
        return price is not None and obj.max_value < price

    def validate(self, attrs):
        return validate_with_model_clean(self, attrs)


class AdminPromotionSerializer(serializers.ModelSerializer):
    """Every field of a promotion, plus live status and payout stats."""

    target_name = serializers.SerializerMethodField()
    is_live = serializers.BooleanField(read_only=True, default=False)
    times_applied = serializers.IntegerField(read_only=True, default=0)
    bonus_points_granted = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Promotion
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "scope",
            "effect",
            "multiplier",
            "bonus_points",
            *_TARGET_FIELDS,
            "target_name",
            "min_order_total",
            "first_order_only",
            *_SCHEDULE_FIELDS,
            "status",
            "is_live",
            "is_deleted",
            "deleted_at",
            "times_applied",
            "bonus_points_granted",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = _ADMIN_READ_ONLY

    def get_target_name(self, obj) -> str | None:
        return _target_name(obj)

    def validate(self, attrs):
        return validate_with_model_clean(self, attrs)


class AdminRedemptionSerializer(RedemptionSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta(RedemptionSerializer.Meta):
        fields = ["user", "user_email", *RedemptionSerializer.Meta.fields]
        read_only_fields = fields


class AdminPointsTransactionSerializer(PointsTransactionSerializer):
    class Meta(PointsTransactionSerializer.Meta):
        fields = [
            *PointsTransactionSerializer.Meta.fields,
            "promotion",
            "redemption",
            "created_by",
        ]
        read_only_fields = fields


class AdminUserLoyaltySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)
    is_guest = serializers.BooleanField(source="user.is_guest", read_only=True)
    current_tier = TierSerializer(read_only=True)
    points_expire_at = serializers.SerializerMethodField()

    class Meta:
        model = UserLoyalty
        fields = [
            "id",
            "user",
            "user_email",
            "user_name",
            "is_guest",
            "balance_points",
            "lifetime_points",
            "orders_completed",
            "total_spent",
            "current_tier",
            "last_activity_at",
            "points_expire_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_points_expire_at(self, obj):
        # The view passes the settings in once so a page of accounts doesn't
        # load them per row.
        return points_expire_at(obj, self.context.get("loyalty_settings"))


class AdjustPointsSerializer(serializers.Serializer):
    points = serializers.IntegerField(
        help_text="Positive to credit, negative to deduct.",
    )
    note = serializers.CharField(
        max_length=255,
        help_text="Why the adjustment was made; shown in the ledger.",
    )

    def validate_points(self, value):
        if value == 0:
            msg = "Adjustment must be non-zero."
            raise serializers.ValidationError(msg)
        return value


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
