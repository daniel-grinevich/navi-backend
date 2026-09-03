from django.core.cache import cache
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.awards.models import ACHIEVEMENTS_LIST_CACHE_KEY
from navi_backend.awards.models import Award
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.rules import metric_value
from navi_backend.core.api import BaseModelViewSet
from navi_backend.core.permissions import ReadOnly

from .serializers import AchievementProgressSerializer
from .serializers import AchievementSerializer
from .serializers import AwardSerializer
from .serializers import LoyaltySettingsSerializer
from .serializers import LoyaltySummarySerializer
from .serializers import PointsTransactionSerializer
from .serializers import TierSerializer
from .serializers import UserAwardSerializer


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
        qs = Award.objects.filter(is_deleted=False)
        if self.request.user.is_staff:
            return qs
        return qs.filter(status=Award.Status.ACTIVE)


class LoyaltySettingsView(APIView):
    """Admin-only view of the program config, including the global
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

    ``GET`` returns balances, tier, next tier and progress toward every award.
    ``PATCH`` lets the user toggle their own award/tier notifications.
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
        return UserAward.objects.filter(user=self.request.user).select_related("award")


class MyPointsTransactionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only points ledger for the current user."""

    serializer_class = PointsTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PointsTransaction.objects.filter(user=self.request.user)


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
        return Award.objects.filter(
            status=Award.Status.ACTIVE,
            is_deleted=False,
        ).order_by("threshold", "name")

    def list(self, request, *args, **kwargs):
        # The active-awards catalogue is identical for every caller and changes
        # only when an admin edits an Award (invalidated in awards.signals).
        data = cache.get(ACHIEVEMENTS_LIST_CACHE_KEY)
        if data is None:
            data = self.get_serializer(self.get_queryset(), many=True).data
            cache.set(ACHIEVEMENTS_LIST_CACHE_KEY, data, 60 * 60)
        return Response(data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def progress(self, request):
        loyalty = UserLoyalty.for_user(request.user)
        earned = {
            ua.award_id: ua.earned_at
            for ua in UserAward.objects.filter(user=request.user)
        }
        rows = []
        for award in self.get_queryset():
            current = int(metric_value(award.rule_type, loyalty))
            target = award.threshold
            rows.append(
                {
                    "id": award.slug,
                    "current": min(current, target) if target else current,
                    "target": target,
                    "unlocked": award.id in earned,
                    "unlocked_at": earned.get(award.id),
                },
            )
        return Response(AchievementProgressSerializer(rows, many=True).data)
