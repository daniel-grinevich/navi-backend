from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from navi_backend.core.api.mixins import TrackUserMixin
from navi_backend.core.permissions import ActionBasedPermission


class BaseModelViewSet(TrackUserMixin, viewsets.ModelViewSet):
    permission_classes = [ActionBasedPermission]
    action_permissions = {
        "default": [IsAuthenticated],
    }
