
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter
import logging

from navi_backend.core.pagination import StandardResultsSetPagination
from navi_backend.fakeapi.api.serializers import OptionSerializer
from navi_backend.fakeapi.api.serializers import (
    ProductSerializer,
    ProductDetailSerializer,
    ProductBulkCreateSerializer,
    ProductBulkUpdateSerializer,
)
from navi_backend.fakeapi.models import Option
from navi_backend.fakeapi.models import Product


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['status','price']
    search_fields = ['name','description']
    ordering_fields = ['name','price','created_at']
    ordering = ['-created_at']

    throttle_classes = [UserRateThrottle, AnonRateThrottle]

    def get_serializer_class(self):
        return ProductSerializer
    
    def get_queryset(self):
        cache_key = f'products_{"admin" if self.request.user.}'



class OptionViewSet(viewsets.ViewSet):
    """
    override get_queryset method to all options
    """

    def get_queryset(self):
        return Option.objects.all()

    def list(self, request):
        queryset = self.get_queryset()
        serializer = OptionSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = self.get_queryset()
        option = get_object_or_404(queryset, pk=pk)
        serializer = OptionSerializer(option)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def search(self, request):
        name = request.query_params.get("name")
        if name:
            queryset = self.get_queryset().filter(name__icontains=name)
            serializer = OptionSerializer(queryset, many=True)
            return Response(serializer.data)
        return Response(
            {"error": "The 'name' query parameter is required."},
            status=400,
        )
