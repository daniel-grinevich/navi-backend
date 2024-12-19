from rest_framework import serializers

from navi_backend.fakeapi.models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["name"]
