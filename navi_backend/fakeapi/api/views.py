from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.viewsets import GenericViewSet

from navi_backend.fakeapi.models import FakeApi

from .serializers import UserSerializer


class FakeApiViewSet(
    RetrieveModelMixin,
    ListModelMixin,
    UpdateModelMixin,
    GenericViewSet,
):
    serializer_class = UserSerializer
    queryset = FakeApi.objects.all()
    lookup_field = "pk"

    # def get_queryset(self, *args, **kwargs):
    #     assert isinstance(self.request.user.id, int)
    #     return self.queryset.filter(id=self.request.user.id)

    # @action(detail=False)
    # def me(self, request):
    #     serializer = UserSerializer(request.user, context={"request": request})
    #     return Response(status=status.HTTP_200_OK, data=serializer.data)
