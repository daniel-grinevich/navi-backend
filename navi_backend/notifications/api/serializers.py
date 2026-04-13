from rest_framework import serializers

from navi_backend.core.api import BaseModelSerializer
from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import EmailTemplate
from navi_backend.notifications.models import TextLog


class EmailLogSerializer(BaseModelSerializer):
    class Meta:
        model = EmailLog
        fields = [
            "id",
            "reason",
            "sent_at",
            "error",
            "meta",
            "is_sent",
            "kind",
            "recipient",
        ]
        read_only_fields = ["id", "sent_at"]


class TextLogSerializer(BaseModelSerializer):
    class Meta:
        model = TextLog
        fields = [
            "id",
            "reason",
            "sent_at",
            "error",
            "meta",
            "is_sent",
            "kind",
            "recipient",
        ]
        read_only_fields = ["id", "sent_at"]


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            "id",
            "subject",
            "body",
            "link",
        ]
