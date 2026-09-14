from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.awards.models import ACHIEVEMENTS_LIST_CACHE_KEY
from navi_backend.awards.models import PROMOTIONS_CACHE_NAMESPACE
from navi_backend.awards.models import REWARDS_CACHE_NAMESPACE
from navi_backend.awards.models import Award
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import Promotion
from navi_backend.awards.models import Reward
from navi_backend.awards.models import RewardRedemption
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.exceptions import InsufficientPointsError
from navi_backend.awards.services.points_service import adjust_points
from navi_backend.awards.services.redemption_service import reverse_redemption
from navi_backend.awards.services.rules import metric_value
from navi_backend.core.api import BaseModelViewSet
from navi_backend.core.api.mixins.track_user_mixin import TrackUserMixin
from navi_backend.core.cache import get_or_set_safe
from navi_backend.core.cache import versioned_key
from navi_backend.core.pagination import StandardResultsSetPagination
from navi_backend.core.permissions import ReadOnly

from .serializers import AchievementProgressSerializer
from .serializers import AchievementSerializer
from .serializers import AdjustPointsSerializer
from .serializers import AdminPointsTransactionSerializer
from .serializers import AdminPromotionSerializer
from .serializers import AdminRedemptionSerializer
from .serializers import AdminRewardSerializer
from .serializers import AdminUserLoyaltySerializer
from .serializers import AwardSerializer
from .serializers import LoyaltySettingsSerializer
from .serializers import LoyaltySummarySerializer
from .serializers import PointsTransactionSerializer
from .serializers import PromotionSerializer
from .serializers import RedemptionSerializer
from .serializers import RewardSerializer
from .serializers import TierSerializer
from .serializers import UserAwardSerializer

# Live lists depend on the clock (schedules open and close on the minute), so
# keep their cache short; admin edits invalidate them immediately via signals.
LIVE_LIST_CACHE_TTL = 60

_TARGET_RELATIONS = ("menu_item", "category", "customization")


class TierViewSet(BaseModelViewSet):
    """Read for any authenticated user; write for staff (admin UI)."""

    serializer_class = TierSerializer
    action_permissions = {
        "default": [ReadOnly | IsAdminUser, IsAuthenticated],
    }

    def get_queryset(self):
        qs = Tier.objects.filter(is_deleted=False)
        if self.request.user.is_staff:
            return qs
        return qs.filter(status=Tier.Status.ACTIVE)


class AwardViewSet(BaseModelViewSet):
    """Read for any authenticated user; write for staff (admin UI)."""

    serializer_class = AwardSerializer
    action_permissions = {
        "default": [ReadOnly | IsAdminUser, IsAuthenticated],
    }

    def get_queryset(self):
        qs = Award.objects.filter(is_deleted=False).prefetch_related("levels")
        if self.request.user.is_staff:
            return qs
        return qs.filter(status=Award.Status.ACTIVE)


class LoyaltySettingsView(APIView):
    """Admin-only view of the program config: earn rate, expiry and the global
    notification kill-switch."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        settings = LoyaltySettings.load()
        return Response(LoyaltySettingsSerializer(settings).data)

    def patch(self, request):
        settings = LoyaltySettings.load()
        serializer = LoyaltySettingsSerializer(
            settings,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MyLoyaltyView(APIView):
    """The current user's loyalty dashboard.

    ``GET`` returns balances, expiry, tier, next tier/reward and progress
    toward every award. ``PATCH`` lets the user toggle their own award/tier
    notifications.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        loyalty = UserLoyalty.for_user(request.user)
        return Response(LoyaltySummarySerializer(loyalty).data)

    def patch(self, request):
        loyalty = UserLoyalty.for_user(request.user)
        # Reward-email opt-in lives on the user's notification preferences now;
        # keep this endpoint working by forwarding the toggle there.
        if "notifications_enabled" in request.data:
            prefs = request.user.preferences
            prefs.email_rewards = bool(request.data["notifications_enabled"])
            prefs.save(update_fields=["email_rewards", "updated_at"])
        return Response(LoyaltySummarySerializer(loyalty).data)


class MyAwardsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only list of the current user's earned awards."""

    serializer_class = UserAwardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            UserAward.objects.filter(user=self.request.user)
            .select_related("award", "level")
            .prefetch_related("award__levels")
        )


class MyPointsTransactionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only points ledger for the current user."""

    serializer_class = PointsTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PointsTransaction.objects.filter(user=self.request.user)


class MyRedemptionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only list of the rewards the current user has redeemed."""

    serializer_class = RedemptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RewardRedemption.objects.filter(user=self.request.user).select_related(
            "reward"
        )


class RewardViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The live rewards catalog, each flagged ``affordable`` for the caller."""

    serializer_class = RewardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Reward.objects.live().select_related(*_TARGET_RELATIONS)

    def list(self, request, *args, **kwargs):
        # The catalog is identical for everyone; only ``affordable`` is
        # per-user, so cache the shared part and add the flag per request.
        rewards = get_or_set_safe(
            versioned_key(REWARDS_CACHE_NAMESPACE, "live"),
            lambda: [
                dict(row)
                for row in self.get_serializer(self.get_queryset(), many=True).data
            ],
            ttl=LIVE_LIST_CACHE_TTL,
        )
        balance = (
            UserLoyalty.objects.filter(user=request.user)
            .values_list("balance_points", flat=True)
            .first()
            or 0
        )
        return Response(
            [
                {**reward, "affordable": balance >= reward["points_cost"]}
                for reward in rewards
            ]
        )


class PromotionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Promotions running right now, for in-app banners."""

    serializer_class = PromotionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Promotion.objects.live().select_related(*_TARGET_RELATIONS)

    def list(self, request, *args, **kwargs):
        data = get_or_set_safe(
            versioned_key(PROMOTIONS_CACHE_NAMESPACE, "live"),
            lambda: [
                dict(row)
                for row in self.get_serializer(self.get_queryset(), many=True).data
            ],
            ttl=LIVE_LIST_CACHE_TTL,
        )
        return Response(data)


class AchievementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Frontend-facing view of the active awards as "achievements".

    ``GET /achievements/`` is public so guests see the catalogue;
    ``GET /achievements/progress/`` returns the authenticated user's progress.
    Both are backed by the existing Award/UserAward models — there is no separate
    achievements table.
    """

    serializer_class = AchievementSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            Award.objects.filter(
                status=Award.Status.ACTIVE,
                is_deleted=False,
            )
            .prefetch_related("levels")
            .order_by("threshold", "name")
        )

    def list(self, request, *args, **kwargs):
        # The active-awards catalogue is identical for every caller and changes
        # only when an admin edits an Award (invalidated in awards.signals).
        # get_or_set_safe keeps a herd of clients from re-serializing it all
        # at once after an invalidation or expiry.
        data = get_or_set_safe(
            ACHIEVEMENTS_LIST_CACHE_KEY,
            lambda: self.get_serializer(self.get_queryset(), many=True).data,
            ttl=60 * 60,
        )
        return Response(data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def progress(self, request):
        loyalty = UserLoyalty.for_user(request.user)
        earned = {
            ua.award_id: ua
            for ua in UserAward.objects.filter(user=request.user).select_related(
                "level",
            )
        }
        rows = []
        for award in self.get_queryset():
            user_award = earned.get(award.id)
            current = int(metric_value(award.rule_type, loyalty))
            levels = award.ordered_levels()
            if levels:
                current_rank = (
                    user_award.level.rank if user_award and user_award.level else 0
                )
                next_level = next(
                    (level for level in levels if level.rank > current_rank),
                    None,
                )
                # Once maxed, target stays at the top level's threshold.
                target = next_level.threshold if next_level else levels[-1].threshold
                level_name = user_award.level.name if user_award else None
                level_rank = user_award.level.rank if user_award else None
                next_level_name = next_level.name if next_level else None
            else:
                target = award.threshold or 0
                level_name = None
                level_rank = None
                next_level_name = None
            rows.append(
                {
                    "id": award.slug,
                    "current": min(current, target) if target else current,
                    "target": target,
                    "unlocked": user_award is not None,
                    "unlocked_at": user_award.earned_at if user_award else None,
                    "level": level_name,
                    "level_rank": level_rank,
                    "next_level": next_level_name,
                },
            )
        return Response(AchievementProgressSerializer(rows, many=True).data)


# ---------------------------------------------------------------------------
# Rewards admin (staff-only, unscoped — for the admin frontend)
# ---------------------------------------------------------------------------


def lifecycle_response(viewset, transition):
    """Run an AuditModel transition (activate/archive/restore) on the object."""
    instance = viewset.get_object()
    try:
        getattr(instance, transition)()
    except DjangoValidationError as exc:
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return Response(viewset.get_serializer(viewset.get_object()).data)


def soft_delete(instance, request):
    instance.soft_delete(
        user_ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.headers.get("user-agent", "")[:200],
    )


class AdminScheduledViewSet(TrackUserMixin, viewsets.ModelViewSet):
    """Shared CRUD shape for rewards and promotions.

    ``destroy`` soft-deletes so redemption/ledger history keeps its FKs. List
    filters (``status``, ``is_live``, ``search``, ``include_deleted`` and the
    subclass extras) come from the model's queryset ``admin_filter``.
    """

    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination

    def base_queryset(self):
        """The Reward/Promotion queryset; each subclass provides its own."""
        raise NotImplementedError

    def annotate_stats(self, queryset):
        return queryset

    def get_queryset(self):
        qs = self.base_queryset().select_related(*_TARGET_RELATIONS)
        if self.action == "list":
            qs = qs.admin_filter(self.request.query_params).order_by("-created_at")
        else:
            qs = qs.annotate_is_live()
        return self.annotate_stats(qs)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._reload_annotated(serializer)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._reload_annotated(serializer)

    def perform_destroy(self, instance):
        soft_delete(instance, self.request)

    def _reload_annotated(self, serializer):
        # Respond with is_live + stats, which only exist on the annotated row.
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return lifecycle_response(self, "activate")

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return lifecycle_response(self, "archive")

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        return lifecycle_response(self, "restore")


class AdminRewardViewSet(AdminScheduledViewSet):
    """Staff CRUD for the rewards catalog. Extra filter: ``target_type``."""

    serializer_class = AdminRewardSerializer

    def base_queryset(self):
        return Reward.objects.all()

    def annotate_stats(self, queryset):
        return queryset.with_redemption_stats()


class AdminPromotionViewSet(AdminScheduledViewSet):
    """Staff CRUD for promotions. Extra filters: ``scope``, ``effect``."""

    serializer_class = AdminPromotionSerializer

    def base_queryset(self):
        return Promotion.objects.all()

    def annotate_stats(self, queryset):
        return queryset.with_bonus_stats()


class AdminRedemptionViewSet(viewsets.ReadOnlyModelViewSet):
    """Every redemption, filterable by ``user``, ``reward``, ``order``,
    ``status``, ``created_after`` and ``created_before``."""

    serializer_class = AdminRedemptionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = RewardRedemption.objects.select_related("user", "reward", "order")
        if self.action == "list":
            qs = qs.admin_filter(self.request.query_params)
        return qs

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        """Refund the points of a redemption (support). The order keeps its
        discount; use this for cancellations that bypassed the normal flow."""
        redemption = self.get_object()
        reversed_now = reverse_redemption(
            redemption,
            created_by=request.user,
            note=f"Reversed by staff: {redemption.reward.name}",
        )
        if not reversed_now:
            return Response(
                {"detail": "This redemption has already been reversed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(redemption).data)


class AdminUserLoyaltyViewSet(viewsets.ReadOnlyModelViewSet):
    """Customer loyalty accounts, searchable by email or name (``search``)."""

    serializer_class = AdminUserLoyaltySerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return (
            UserLoyalty.objects.select_related("user", "current_tier")
            .search(self.request.query_params.get("search"))
            .order_by("-lifetime_points", "created_at")
        )

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            "loyalty_settings": LoyaltySettings.load(),
        }

    @action(detail=True, methods=["get"])
    def transactions(self, request, pk=None):
        loyalty = self.get_object()
        entries = PointsTransaction.objects.filter(user_id=loyalty.user_id)
        page = self.paginate_queryset(entries)
        serializer = AdminPointsTransactionSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        loyalty = self.get_object()
        payload = AdjustPointsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            entry = adjust_points(
                loyalty,
                payload.validated_data["points"],
                note=payload.validated_data["note"],
                staff_user=request.user,
            )
        except InsufficientPointsError:
            return Response(
                {"points": ["This would take the balance below zero."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "account": self.get_serializer(loyalty).data,
                "transaction": AdminPointsTransactionSerializer(entry).data,
            },
            status=status.HTTP_201_CREATED,
        )
