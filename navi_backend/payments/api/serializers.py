from rest_framework import serializers

from navi_backend.core.api.mixins import ReadOnlyAuditMixin
from navi_backend.payments.models import Payment


class PaymentSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "stripe_payment_intent_id",
            "amount_received",
            "currency",
            "status",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]


class PaymentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "stripe_payment_intent_id",
            "amount_received",
            "currency",
            "status",
        ]
