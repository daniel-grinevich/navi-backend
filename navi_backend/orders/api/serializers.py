from django.db import transaction
from rest_framework import serializers
from .mixins import ReadOnlyAuditMixin

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
from navi_backend.users.api.serializers import UserSerializer


class OrderCustomizationSerializer(serializers.ModelSerializer):
    order_item = serializers.PrimaryKeyRelatedField(read_only=True)
    unit_price = serializers.DecimalField(
        read_only=True, max_digits=8, decimal_places=2
    )

    class Meta:
        model = OrderCustomization
        fields = [
            "order_item",
            "customization",
            "quantity",
            "unit_price",
        ]


class OrderItemSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
    customizations = OrderCustomizationSerializer(many=True, required=False)
    unit_price = serializers.DecimalField(
        read_only=True, max_digits=8, decimal_places=2
    )

    class Meta:
        model = OrderItem
        fields = [
            "menu_item",
            "order",
            "customizations",
            "unit_price",
            "quantity",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]


class OrderSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):

    items = OrderItemSerializer(many=True, required=False)
    user = UserSerializer(read_only=True)

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
            "items",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        user = self.context["request"].user
        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            for item_data in items_data:
                customizations_data = item_data.pop("customizations", [])
                menu_item = item_data["menu_item"]
                order_item = OrderItem.objects.create(
                    unit_price=menu_item.price,
                    created_by=user,
                    updated_by=user,
                    order=order,
                    **item_data
                )
                for customization_data in customizations_data:
                    customization = customization_data["customization"]
                    OrderCustomization.objects.create(
                        unit_price=customization.price,
                        created_by=user,
                        updated_by=user,
                        order_item=order_item,
                        **customization_data
                    )

        return order


class MenuItemIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItemIngredient
        fields = [
            "menu_item",
            "ingredient",
            "quantity",
            "unit",
        ]


class CustomizationSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class NaviPortSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class PaymentTypeSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class IngredientSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class MenuItemSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class RasberryPiSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class EspressoMachineSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class MachineTypeSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class CustomizationGroupSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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


class CategorySerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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
