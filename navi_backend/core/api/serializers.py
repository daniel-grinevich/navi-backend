from rest_framework import serializers

from .mixins import ReadOnlyAuditMixin
from .mixins import ShowOnlyToAdminFieldsMixin
from .mixins import ViewFilterMixin


class BaseModelSerializer(
    ViewFilterMixin,
    ShowOnlyToAdminFieldsMixin,
    ReadOnlyAuditMixin,
    serializers.ModelSerializer,
):
    class Meta:
        abstract = True


class BaseSerializer(serializers.Serializer):
    pass
