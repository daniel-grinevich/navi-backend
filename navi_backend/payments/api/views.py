from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from navi_backend.orders.api.mixins import TrackUserMixin
from navi_backend.payments.api.serializers import PaymentCreateSerializer
from navi_backend.payments.api.serializers import PaymentSerializer
from navi_backend.payments.models import Payment


class PaymentViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentCreateSerializer
        return PaymentSerializer
