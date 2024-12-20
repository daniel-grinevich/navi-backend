from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from navi_backend.fakeapi.api.serializers import OptionSerializer
from navi_backend.fakeapi.api.serializers import ProductSerializer
from navi_backend.fakeapi.models import Option
from navi_backend.fakeapi.models import Product


class ProductViewSet(viewsets.ViewSet):
    def get_queryset(self):
        """
        override get_queryset method to all products
        """
        return Product.objects.all()

    # Built in function list -> think of this like a root url
    def list(self, request):
        queryset = self.get_queryset()
        serializer = ProductSerializer(queryset, many=True)
        return Response(serializer.data)

    # Use a action to get by name
    @action(detail=False, methods=["get"])
    def search(self, request):
        # Filter products by 'name' query parameter
        name = request.query_params.get("name", None)
        if name:
            queryset = self.get_queryset().filter(name__icontains=name)
            serializer = ProductSerializer(queryset, many=True)
            return Response(serializer.data)
        return Response({"error": "No name parameter provided"}, status=400)

    def retrieve(self, request, pk=None):
        # Retrieve a single product by Id
        queryset = self.get_queryset()
        product = get_object_or_404(queryset, pk=pk)
        serializer = ProductSerializer(product)
        return Response(serializer.data)


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
