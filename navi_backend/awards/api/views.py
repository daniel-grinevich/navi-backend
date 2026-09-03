from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.awards.models import Award
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import PointsTransaction
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.core.api import BaseModelViewSet
from navi_backend.core.permissions import ReadOnly

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
        serializer = LoyaltySummarySerializer(
            loyalty,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


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
