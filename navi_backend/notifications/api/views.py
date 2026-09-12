from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from navi_backend.core.api.mixins.track_user_mixin import TrackUserMixin
from navi_backend.notifications.api.serializers import EmailLogSerializer
from navi_backend.notifications.api.serializers import EmailTemplateSerializer
from navi_backend.notifications.api.serializers import TextLogSerializer
from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import EmailTemplate
from navi_backend.notifications.models import TextLog


class EmailLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Delivery logs are written by the system, not authored via the API.

    Admins read them for auditing; creation/editing is intentionally disabled
    (the old writable viewset stamped created_by/updated_by fields the log
    models never had, which 500'd on every write).
    """

    queryset = EmailLog.objects.all()
    serializer_class = EmailLogSerializer
    permission_classes = [IsAdminUser]


class TextLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TextLog.objects.all()
    serializer_class = TextLogSerializer
    permission_classes = [IsAdminUser]


class EmailTemplateViewSet(TrackUserMixin, viewsets.ModelViewSet):
    """Admin-authored, so writes are allowed and attributed via TrackUserMixin
    (EmailTemplate now carries created_by/updated_by)."""

    queryset = EmailTemplate.objects.all()
    serializer_class = EmailTemplateSerializer
    permission_classes = [IsAdminUser]
