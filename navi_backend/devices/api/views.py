from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from navi_backend.devices.api.serializers import EspressoMachineSerializer
from navi_backend.devices.api.serializers import MachineTypeSerializer
from navi_backend.devices.api.serializers import NaviPortSerializer
from navi_backend.devices.api.serializers import RaspberryPiSerializer
from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.orders.api.mixins import TrackUserMixin
from navi_backend.orders.api.utils import get_parent_pk


class NaviPortViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = NaviPort.objects.all()
    serializer_class = NaviPortSerializer
    permission_classes = [IsAdminUser]


class RaspberryPiViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = RaspberryPiSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = get_parent_pk(self.request.path, "navi_ports")
        navi_port = NaviPort.objects.filter(pk=navi_port_pk).first()
        if not navi_port:
            return RaspberryPi.objects.none()

        return RaspberryPi.objects.filter(navi_port__pk=navi_port_pk)


class EspressoMachineViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = EspressoMachineSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = get_parent_pk(self.request.path, "navi_ports")
        navi_port = NaviPort.objects.filter(pk=navi_port_pk).first()
        if not navi_port:
            return EspressoMachine.objects.none()

        return EspressoMachine.objects.filter(navi_port__pk=navi_port_pk)


class MachineTypeViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = MachineTypeSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        espresso_machine_pk = get_parent_pk(self.request.path, "espresso_machines")
        espresso_machine = EspressoMachine.objects.filter(
            pk=espresso_machine_pk
        ).first()
        if not espresso_machine:
            return MachineType.objects.none()

        return MachineType.objects.filter(espresso_machine__pk=espresso_machine_pk)
