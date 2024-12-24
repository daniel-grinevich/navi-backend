from rest_framework import serializers

from navi_backend.fakeapi.models import Option
from navi_backend.fakeapi.models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
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
