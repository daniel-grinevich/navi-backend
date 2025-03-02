from rest_framework import serializers

from navi_backend.fakeapi.models import Option
from navi_backend.fakeapi.models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "price",
            "description",
            "body",
            "status",
            "image",
            "is_featured",
            "view_count",
            "version",
            "is_deleted",
            "last_modified_ip",
            "last_modified_user_agent",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = [
            "name",
            "price",
            "description",
            "body",
            "status",
            "image",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]