from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from navi_backend.notifications.api.serializers import EmailLogSerializer
from navi_backend.notifications.api.serializers import EmailTemplateSerializer
from navi_backend.notifications.api.serializers import TextLogSerializer
from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import EmailTemplate
from navi_backend.notifications.models import TextLog
from navi_backend.orders.api.mixins import TrackUserMixin


class EmailLogViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = EmailLog.objects.all()
    serializer_class = EmailLogSerializer
    permission_classes = [IsAdminUser]


class TextLogViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = TextLog.objects.all()
    serializer_class = TextLogSerializer
    permission_classes = [IsAdminUser]


class EmailTemplateViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = EmailTemplate.objects.all()
    serializer_class = EmailTemplateSerializer
    permission_classes = [IsAdminUser]
