from django.core.cache import cache
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from drf_spectacular.utils import extend_schema
import logging

from navi_backend.core.pagination import StandardResultsSetPagination
from navi_backend.fakeapi.api.serializers import ProductSerializer
from navi_backend.fakeapi.models import Product

logger = logging.getLogger(__name__)


class ProductViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing Product objects.

    Provides CRUD operations and additional actions for Product management.
    Supports filtering, searching, ordering, and pagination.
    """
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    search_fields = ['name', 'description', 'body']
    ordering_fields = ['name', 'price', 'created_at', 'view_count']
    ordering = ['-created_at']
    throttle_classes = [UserRateThrottle, AnonRateThrottle]

    def get_queryset(self):
        """
        Return cached queryset based on user permissions.
        - Admin users see all products including deleted ones
        - Regular users only see active, non-deleted products
        """
        user = self.request.user
        is_admin = user.is_authenticated and user.is_staff

        # Define cache key based on user role
        cache_key = f'products_{"admin" if is_admin else "regular"}'

        # Try to get from cache first
        queryset = cache.get(cache_key)
        if queryset is not None:
            return queryset

        # Determine base queryset
        if is_admin:
            queryset = Product.objects.all()
        else:
            queryset = Product.objects.filter(
                is_deleted=False,
                status=Product.Status.ACTIVE
            )

        # Add select_related for performance optimization
        queryset = queryset.select_related('created_by', 'updated_by')

        # Cache for a short period (5 minutes)
        cache.set(cache_key, queryset, timeout=300)

        return queryset

    def perform_create(self, serializer):
        """Add current user as created_by and updated_by"""
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )
        logger.info(
            f"Product created: {serializer.instance.name} by {self.request.user}"
        )
        # Invalidate cache after creating a product
        cache.delete_many(['products_admin', 'products_regular'])

    def perform_update(self, serializer):
        """Update updated_by field and record IP and user agent"""
        # Get client IP and User-Agent
        user_ip = self.request.META.get('REMOTE_ADDR')
        user_agent = self.request.META.get('HTTP_USER_AGENT')
        
        serializer.save(
            updated_by=self.request.user,
            last_modified_ip=user_ip,
            last_modified_user_agent=user_agent
        )
        logger.info(
            f"Product updated: {serializer.instance.name} by {self.request.user}"
        )
        # Invalidate cache after updating a product
        cache.delete_many(['products_admin', 'products_regular'])
    def perform_destroy(self, instance):
        """
        Override destroy to implement soft delete instead of hard delete
        """
        user_ip = self.request.META.get('REMOTE_ADDR')
        user_agent = self.request.META.get('HTTP_USER_AGENT')

        # Use soft_delete method from the model
        instance.soft_delete(user_ip=user_ip, user_agent=user_agent)
        logger.info(
            f"Product soft deleted: {instance.name} by {self.request.user}"
        )
        # Invalidate cache after soft-deleting a product
        cache.delete_many(['products_admin', 'products_regular'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        description="Retrieve a list of featured products",
        responses={200: ProductSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured products"""
        queryset = Product.objects.filter(
            is_featured=True,
            is_deleted=False,
            status=Product.Status.ACTIVE
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Increment product view count",
        responses={200: {"description": "View count incremented"}}
    )
    @action(detail=True, methods=['post'])
    def view(self, request, pk=None):
        """Increment product view count"""
        product = self.get_object()
        product.increment_view_count()
        return Response({"status": "View count incremented"})
