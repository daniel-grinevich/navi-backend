from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response


from .utils import getParentPK
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
        if self.action in [
            "list",
            "retrieve",
            "update",
            "partial_update",
            "cancel_order",
        ]:
            permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
        elif self.action == "create":
            permission_classes = [IsAuthenticated]
        elif self.action in ["destroy", "send_order_to_navi_port"]:
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

    @action(detail=True, methods=["put"], name="Cancel Order")
    def cancel_order(self, request, pk=None):
        """Cancels an order if it's in an ordered state ('O')."""
        print(self.get_queryset())
        order = get_object_or_404(self.get_queryset(), pk=pk)

        if order.status != "O":
            return Response(
                {"detail": "Order could not be cancelled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        order.status = "C"
        order.save()
        return Response(
            {"detail": "Order cancelled successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], name="Retrieve and Mark Order as Sent")
    def send_order_to_navi_port(self, request, pk=None):
        """
        GET: Return order details and update status to 'sent' ('S').
        """
        order = get_object_or_404(self.get_queryset(), pk=pk)

        if order.status == "S":
            return Response(
                {"detail": "Order is already sent."},
                status=status.HTTP_200_OK,
            )

        if order.status != "O":  # 'O' = Open
            return Response(
                {"detail": "Order cannot be sent."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Update status to "Sent"
        order.status = "S"
        order.save()

        # Return updated order details
        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
        order_pk = getParentPK(self.request.path, "orders")
        order = Order.objects.filter(pk=order_pk).first()
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
    serializer_class = EspressoMachineSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = getParentPK(self.request.path, "navi_ports")
        navi_port = NaviPort.objects.filter(pk=navi_port_pk).first()
        if not navi_port:
            return NaviPort.objects.none()

        return NaviPort.objects.filter(navi_port_id=navi_port_pk)


class MachineTypeMachineViewSet(viewsets.ModelViewSet):
    serializer_class = MachineTypeSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = getParentPK(self.request.path, "navi_ports")
        navi_port = NaviPort.objects.filter(pk=navi_port_pk).first()
        if not navi_port:
            return NaviPort.objects.none()

        return NaviPort.objects.filter(navi_port_id=navi_port_pk)
