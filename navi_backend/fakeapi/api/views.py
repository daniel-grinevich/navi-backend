# from rest_framework.mixins import ListModelMixin
# from rest_framework.mixins import RetrieveModelMixin
# from rest_framework.mixins import UpdateModelMixin
from rest_framework import viewsets
from rest_framework.response import Response

from navi_backend.fakeapi.api.serializers import ProductSerializer
from navi_backend.fakeapi.models import Product


class FakeApiViewSet(viewsets.ViewSet):
    def list(self, request):
        queryset = Product.objects.all()
        serializer = ProductSerializer(queryset, many=True)
        return Response(serializer.data)
