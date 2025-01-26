from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from navi_backend.orders.models import Order, MenuItem

from .serializers import OrderSerializer, MenuItemSerializer


class MenuItemViewSet(viewsets.ViewSet):
    def get_queryset(self):
        """
        override get_queryset method to all Orders
        """
        return MenuItem.objects.all()

    # Built in function list -> think of this like a root url
    def list(self, request):
        queryset = self.get_queryset()
        serializer = MenuItemSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        # Retrieve a single product by Id
        queryset = self.get_queryset()
        product = get_object_or_404(queryset, pk=pk)
        serializer = MenuItemSerializer(product)
        return Response(serializer.data)


class OrderViewSet(viewsets.ViewSet):
    def get_queryset(self):
        """
        override get_queryset method to all Orders
        """
        return Order.objects.all()

    # Built in function list -> think of this like a root url
    def list(self, request):
        queryset = self.get_queryset()
        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        # Retrieve a single product by Id
        queryset = self.get_queryset()
        product = get_object_or_404(queryset, pk=pk)
        serializer = OrderSerializer(product)
        return Response(serializer.data)
