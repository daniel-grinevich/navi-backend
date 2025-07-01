import stripe
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from navi_backend.orders.models import Category
from navi_backend.orders.models import Customization
from navi_backend.orders.models import CustomizationGroup
from navi_backend.orders.models import EspressoMachine
from navi_backend.orders.models import Ingredient
from navi_backend.orders.models import MachineType
from navi_backend.orders.models import MenuItem
from navi_backend.orders.models import MenuItemIngredient
from navi_backend.orders.models import NaviPort
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.orders.models import RasberryPi
from navi_backend.users.api.serializers import UserSerializer

from .mixins import ReadOnlyAuditMixin


class OrderCustomizationSerializer(serializers.ModelSerializer):
    order_item = serializers.PrimaryKeyRelatedField(read_only=True)
    unit_price = serializers.DecimalField(
        read_only=True, max_digits=8, decimal_places=2
    )
    customization = serializers.SlugRelatedField(
        slug_field="name", queryset=Customization.objects.all()
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
    menu_item = serializers.SlugRelatedField(
        slug_field="name", queryset=MenuItem.objects.all()
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
            "auth_token",
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
        order_item_payload = validated_data.pop("items", [])
        print(f"order_item_payload {order_item_payload}")
        user = self.context["request"].user

        try:
            with transaction.atomic():
                order = Order.objects.create(**validated_data)
                order.auth_token = (
                    self.context["request"].headers["Authorization"].split()[1] or None
                )
                order.save(update_fields=["auth_token"])

                for order_item in order_item_payload:
                    customizations_data = order_item.pop("customizations", [])
                    menu_item = order_item["menu_item"]
                    created_order_item = OrderItem.objects.create(
                        unit_price=menu_item.price,
                        quantity=order_item["quantity"],
                        created_by=user,
                        updated_by=user,
                        order=order,
                        menu_item=menu_item,
                    )
                    for customization_data in customizations_data:
                        customization = customization_data["customization"]
                        OrderCustomization.objects.create(
                            unit_price=customization.price,
                            created_by=user,
                            updated_by=user,
                            order_item=created_order_item,
                            **customization_data,
                        )
                try:
                    intent = stripe.PaymentIntent.create(order)
                    order.payment = intent["client_secret"]
                    order.save(update_fields=["payment"])
                except stripe.error.StripeError as e:
                    raise ValidationError({"payment": f"Stripe error: {e!s}"}) from e
        except Exception as e:
            raise ValidationError({"error": str(e)}) from e

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
        source="menu_item_ingredients",
        read_only=True,
    )

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "slug",
            "name",
            "status",
            "category_name",
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
    customizations = CustomizationSerializer(
        source="customization_set",
        many=True,
        read_only=True,
    )

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
            "customizations",
        ]


class CategoryCustomizationSerializer(serializers.ModelSerializer):
    customization_groups = CustomizationGroupSerializer(
        source="customizationgroup_set",
        many=True,
        read_only=True,
    )

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "customization_groups"]


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


class MenuItemCustomizationSerialier(ReadOnlyAuditMixin, serializers.ModelSerializer):
    category = CategoryCustomizationSerializer(read_only=True)
    ingredients = MenuItemIngredientSerializer(
        many=True,
        source="menu_item_ingredients",
        read_only=True,
    )

    class Meta:
        model = MenuItem
        fields = [
            "name",
            "slug",
            "status",
            "category",
            "image",
            "body",
            "description",
            "price",
            "ingredients",
        ]
