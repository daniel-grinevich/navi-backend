from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from navi_backend.core.permissions import ReadOnly
from navi_backend.menu.api.serializers import CategorySerializer
from navi_backend.menu.api.serializers import CustomizationGroupSerializer
from navi_backend.menu.api.serializers import CustomizationSerializer
from navi_backend.menu.api.serializers import MenuItemCustomizationSerializer
from navi_backend.menu.api.serializers import MenuItemIngredientSerializer
from navi_backend.menu.api.serializers import MenuItemSerializer
from navi_backend.menu.models import Category
from navi_backend.menu.models import Customization
from navi_backend.menu.models import CustomizationGroup
from navi_backend.menu.models import Ingredient
from navi_backend.menu.models import MenuItem
from navi_backend.menu.models import MenuItemIngredient
from navi_backend.orders.api.mixins import TrackUserMixin


class MenuItemViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAdminUser | ReadOnly]

    @action(
        detail=False,
        methods=["get"],
        url_path=r"(?P<slug>[^/.]+)/category-customizations",
    )
    def category_customizations(self, request, slug=None):
        """
        GET /menu_items/<slug>/category-customizations/
        """
        menu_item = get_object_or_404(MenuItem, slug=slug)
        if not menu_item.category:
            return Response(
                {"detail": "No category for that menu-item."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = MenuItemCustomizationSerializer(
            menu_item, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def add_ingredient(self, request, pk=None):
        """
        Adds an ingredient to a specific MenuItem.
        """
        menu_item = self.get_object()

        ingredient_id = request.data.get("ingredient_id")
        quantity = request.data.get("quantity")
        unit = request.data.get("unit")

        if not (ingredient_id and quantity and unit):
            return Response(
                {"error": "ingredient_id, quantity, and unit are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ingredient = Ingredient.objects.filter(id=ingredient_id).first()

        if not ingredient:
            return Response(
                {"error": "Invalid ingredient ID"},
                status=status.HTTP_404_NOT_FOUND,
            )

        menu_item_ingredient, created = MenuItemIngredient.objects.update_or_create(
            menu_item=menu_item,
            ingredient=ingredient,
            defaults={"quantity": quantity, "unit": unit},
        )

        return Response(
            MenuItemIngredientSerializer(menu_item_ingredient).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def ingredients(self, request, pk=None):
        """
        Retrieve all ingredients for a specific MenuItem.
        """
        menu_item = self.get_object()
        ingredients = menu_item.menu_item_ingredients.select_related("ingredient")
        return Response(MenuItemIngredientSerializer(ingredients, many=True).data)


class CustomizationViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = Customization.objects.all()
    serializer_class = CustomizationSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class CustomizationGroupViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = CustomizationGroup.objects.all()
    serializer_class = CustomizationGroupSerializer
    permission_classes = [IsAdminUser | ReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        category_name = self.request.query_params.get("category_name")

        if category_name is None:
            return qs

        return qs.filter(category__name=category_name)


class CategoryViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUser | ReadOnly]
