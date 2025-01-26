from rest_framework import serializers
from navi_backend.orders.models import (
    Order,
    MenuItem,
    OrderCustomization,
    Customization,
    OrderItem,
)


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            "user",
            "paymentType",
            "port",
            "totalPrice",
            "created_at",
            "slug",
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "menuitem",
            "order",
            "price",
            "name",
            "qty",
            "slug",
        ]


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = [
            "name",
            "category",
            "description",
            "price",
            "image",
            "created_at",
            "slug",
        ]


class OrderCustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderCustomization
        fields = [
            "name",
            "order_item",
            "customization",
            "qty",
            "slug",
        ]


class CustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customization
        fields = [
            "name",
            "group",
            "slug",
        ]
