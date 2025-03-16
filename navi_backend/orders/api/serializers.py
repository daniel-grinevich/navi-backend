from rest_framework import serializers
from navi_backend.orders.models import (
    Order,
    MenuItem,
    OrderCustomization,
    Customization,
    OrderItem,
    NaviPort,
    PaymentType,
    Ingredient,
    MenuItemIngredient,
)


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            "user",
            "payment_type",
            "navi_port",
            "price",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "menu_item",
            "order",
            "unit_price",
            "quantity",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]


class MenuItemIngredientSerializer(serializers.ModelSerializer):

    class Meta:
        model = MenuItemIngredient
        fields = [
            "menu_item",
            "ingredient",
            "quantity",
            "unit",
        ]


class MenuItemSerializer(serializers.ModelSerializer):
    ingredients = MenuItemIngredientSerializer(
        many=True,
        source="menu_item_ingredients",  # Related name from model
        read_only=True,
    )

    class Meta:
        model = MenuItem
        fields = [
            "name",
            "category",
            "description",
            "price",
            "image",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
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


class NaviPortSerializer(serializers.ModelSerializer):
    class Meta:
        model = NaviPort
        fields = [
            "name",
            "slug",
        ]


class PaymentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentType
        fields = [
            "name",
            "slug",
        ]


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = [
            "name",
            "description",
            "slug",
            "name",
            "description",
            "is_allergen",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]


class MenuItemSerializer(serializers.ModelSerializer):
    ingredients = MenuItemIngredientSerializer(
        many=True,
        source="menu_item_ingredients",  # Related name from model
        read_only=True,
    )

    class Meta:
        model = MenuItem
        fields = [
            "slug",
            "name",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "image",
            "body",
            "description",
            "price",
            "ingredients",
        ]
