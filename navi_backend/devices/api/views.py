from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from navi_backend.devices.api.serializers import EspressoMachineSerializer
from navi_backend.devices.api.serializers import MachineTypeSerializer
from navi_backend.devices.api.serializers import NaviPortSerializer
from navi_backend.devices.api.serializers import RaspberryPiSerializer
from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.orders.api.mixins import TrackUserMixin


class NaviPortViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = NaviPort.objects.all()
    serializer_class = NaviPortSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class RaspberryPiViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = RaspberryPiSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = self.kwargs.get("navi_port_pk")
        return RaspberryPi.objects.filter(navi_port__pk=navi_port_pk)


class EspressoMachineViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = EspressoMachineSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = self.kwargs.get("navi_port_pk")
        return EspressoMachine.objects.filter(navi_port__pk=navi_port_pk)


class MachineTypeViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = MachineType.objects.all()
    serializer_class = MachineTypeSerializer
    permission_classes = [IsAdminUser]
