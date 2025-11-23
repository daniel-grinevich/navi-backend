from rest_framework import serializers

from navi_backend.core.api.serializers import ReadOnlyAuditMixin
from navi_backend.menu.models import Category
from navi_backend.menu.models import Customization
from navi_backend.menu.models import CustomizationGroup
from navi_backend.menu.models import MenuItem
from navi_backend.menu.models import MenuItemIngredient


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
            "body",
            "description",
            "price",
            "ingredients",
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


class MenuItemCustomizationSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
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
            "body",
            "description",
            "price",
            "ingredients",
        ]
