from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from navi_backend.orders.models import (
    Order,
    MenuItem,
    NaviPort,
    PaymentType,
    OrderItem,
    OrderCustomization,
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
)


class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAdminUser | ReadOnly]


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
        order_id = self.kwargs.get("order_id")
        order = Order.objects.filter(id=order_id).first()

        if not order:
            return (
                OrderItem.objects.none()
            )  # Return empty queryset if order doesn't exist

        if self.request.user.is_staff or order.user == self.request.user:
            return OrderItem.objects.filter(order_id=order_id)

        return OrderItem.objects.none()  # Unauthorized users get an empty queryset


class NaviPortViewSet(viewsets.ModelViewSet):
    queryset = NaviPort.objects.all()
    serializer_class = NaviPortSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class PaymentTypeViewSet(viewsets.ModelViewSet):
    queryset = PaymentType.objects.all()
    serializer_class = PaymentTypeSerializer
    permission_classes = [IsAdminUser | ReadOnly]
