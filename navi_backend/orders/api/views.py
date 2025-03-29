import re
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from navi_backend.orders.models import (
    Order,
    MenuItem,
    NaviPort,
    PaymentType,
    OrderItem,
    OrderCustomization,
    MenuItemIngredient,
    Ingredient,
    RasberryPi,
    MachineType,
    EspressoMachine,
    Customization,
    CustomizationGroup,
)
from rest_framework.permissions import (
    IsAuthenticated,
    IsAdminUser,
    IsAuthenticatedOrReadOnly,
)
from .permissions import ReadOnly, IsOwnerOrAdmin

from .serializers import (
    OrderSerializer,
    MenuItemSerializer,
    NaviPortSerializer,
    PaymentTypeSerializer,
    OrderItemSerializer,
    MenuItemIngredientSerializer,
    IngredientSerializer,
    EspressoMachineSerializer,
    MachineTypeSerializer,
    RasberryPiSerializer,
)


class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAdminUser | ReadOnly]

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

        # Create or update the ingredient in the recipe
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


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer

    def get_permissions(self):
        """
        Assign different permissions for actions.
        """
        if self.action in ["list", "retrieve", "update", "partial_update"]:
            permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
        elif self.action == "create":
            permission_classes = [IsAuthenticated]
        elif self.action == "destroy":
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [IsAuthenticated]  # Default for other actions
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """
        Restrict queryset to the user's own orders unless the user is an admin.
        """
        if self.request.user.is_staff:
            return Order.objects.all()  # Admins can access all orders
        return Order.objects.filter(
            user=self.request.user
        )  # Users can only see their own orders

    def perform_create(self, serializer):
        """
        Set the `user` field to the currently authenticated user.
        """
        serializer.save(user=self.request.user)


class OrderItemViewSet(viewsets.ModelViewSet):
    serializer_class = OrderItemSerializer

    def get_queryset(self):
        """
        Restrict query to order items belonging to a specific order.
        - Admins can access all orders.
        - Regular users can only access their own order items.
        """
        path = self.request.path
        order_pk = ""
        match = re.search(r"/orders/(\d+)/items", path)
        if match:
            order_pk = match.group(1)
        # order_item = OrderItem.objects.filter(pk=order_item_id)
        order = Order.objects.filter(pk=order_pk).first()
        print("ORDER", self.kwargs, "URL ", self.request)
        if not order:
            return (
                OrderItem.objects.none()
            )  # Return empty queryset if order doesn't exist

        if self.request.user.is_staff or order.user == self.request.user:
            return OrderItem.objects.filter(order_id=order_pk)

        return OrderItem.objects.none()  # Unauthorized users get an empty queryset


class NaviPortViewSet(viewsets.ModelViewSet):
    queryset = NaviPort.objects.all()
    serializer_class = NaviPortSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class PaymentTypeViewSet(viewsets.ModelViewSet):
    queryset = PaymentType.objects.all()
    serializer_class = PaymentTypeSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class MenuItemIngredientViewSet(viewsets.ModelViewSet):
    queryset = MenuItemIngredient.objects.select_related("menu_item", "ingredient")
    serializer_class = MenuItemIngredientSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class IngredientViewSet(viewsets.ModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class RasberryPiViewSet(viewsets.ModelViewSet):
    queryset = RasberryPi.objects.all()
    serializer_class = RasberryPiSerializer
    permission_classes = [IsAdminUser]


class EspressoMachineViewSet(viewsets.ModelViewSet):
    queryset = EspressoMachine.objects.all()
    serializer_class = EspressoMachineSerializer
    permission_classes = [IsAdminUser]
