from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from navi_backend.orders.models import Order, MenuItem
from rest_framework.permissions import (
    IsAuthenticated,
    IsAdminUser,
    IsAuthenticatedOrReadOnly,
)
from .permissions import ReadOnly, IsOwnerOrAdmin

from .serializers import OrderSerializer, MenuItemSerializer


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
        if self.action in ["list", "retrieve", "update", "partial_update", "destroy"]:
            permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
        elif self.action == "create":
            permission_classes = [IsAuthenticated]
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
