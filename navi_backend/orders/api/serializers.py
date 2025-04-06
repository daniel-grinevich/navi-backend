from rest_framework import serializers

from navi_backend.orders.models import (
    Order,
    MenuItem,
    OrderCustomization,
    Customization,
    CustomizationGroup,
    Category,
    OrderItem,
    NaviPort,
    PaymentType,
    Ingredient,
    MenuItemIngredient,
    RasberryPi,
    EspressoMachine,
    MachineType,
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


class OrderCustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderCustomization
        fields = [
            "order_item",
            "customization",
            "quantity",
            "unit_price",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        ]


class CustomizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customization
        fields = [
            "name",
            "group",
            "description",
            "display_order",
            "price",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]


class NaviPortSerializer(serializers.ModelSerializer):
    class Meta:
        model = NaviPort
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "rasberry_pi",
            "espresso_machine",
        ]


class PaymentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentType
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
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


class RasberryPiSerializer(serializers.ModelSerializer):
    class Meta:
        model = RasberryPi
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "mac_address",
            "ip_address",
            "location",
            "is_connected",
            "firmware_version",
            "last_seen",
        ]


class EspressoMachineSerializer(serializers.ModelSerializer):
    class Meta:
        model = EspressoMachine
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "serial_number",
            "machine_type",
            "ip_address",
            "port",
            "is_online",
            "last_maintenance_at",
        ]


class MachineTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineType
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "model_number",
            "maintenance_frequency",
            "supported_drinks",
        ]


class CustomizationGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomizationGroup
        fields = [
            "name",
            "category",
            "description",
            "display_order",
            "is_required",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "name",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]
