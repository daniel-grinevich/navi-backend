from rest_framework import serializers

from navi_backend.core.api import BaseModelSerializer
from navi_backend.notifications.models import ALWAYS_ON_CATEGORIES
from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import EmailTemplate
from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
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


def _reject_unknown_keys(value, allowed, label):
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        msg = f"unknown {label}: {', '.join(unknown)}"
        raise serializers.ValidationError(msg)


class NotificationSettingsUpdateSerializer(serializers.Serializer):
    """PATCH body: any subset of channel/category switches."""

    channels = serializers.DictField(child=serializers.BooleanField(), required=False)
    categories = serializers.DictField(
        child=serializers.BooleanField(),
        required=False,
    )

    def validate_channels(self, value):
        _reject_unknown_keys(value, NotificationKind.values, "channel")
        return value

    def validate_categories(self, value):
        _reject_unknown_keys(value, NotificationCategory.values, "category")
        for category in ALWAYS_ON_CATEGORIES:
            if value.get(category) is False:
                msg = f"{category} notifications cannot be disabled"
                raise serializers.ValidationError(msg)
        return value


class NotificationSettingsSerializer(serializers.Serializer):
    """Read shape: ``{"channels", "categories", "updated_at", "updated_by"}``."""

    def to_representation(self, instance):
        updated_by = instance.updated_by
        return {
            "channels": {
                kind: instance.channel_enabled(kind) for kind in NotificationKind
            },
            "categories": {
                category: instance.category_enabled(category)
                for category in NotificationCategory
            },
            "updated_at": serializers.DateTimeField().to_representation(
                instance.updated_at,
            ),
            "updated_by": updated_by.email if updated_by else None,
        }
