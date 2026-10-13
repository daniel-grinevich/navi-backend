from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.core.api.mixins.track_user_mixin import TrackUserMixin
from navi_backend.devices.api.serializers import EspressoMachineSerializer
from navi_backend.devices.api.serializers import MachineTypeSerializer
from navi_backend.devices.api.serializers import NaviPortAvailabilitySerializer
from navi_backend.devices.api.serializers import NaviPortSerializer
from navi_backend.devices.api.serializers import RaspberryPiSerializer
from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services.port_status import build_port_status
from navi_backend.devices.services.port_status import get_port_status_by_slug


class NaviPortViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = NaviPort.objects.select_related("espresso_machine", "raspberry_pi")
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


class NaviPortBySlugView(APIView):
    """Public status for the port behind a machine's sticker QR (/p/<slug>)."""

    # Anonymous walk-up customers; skip cookie auth so a stale/expired session
    # cookie can't turn this public read into a 401.
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        data = get_port_status_by_slug(slug)
        if data is None:
            msg = "No machine found for this code."
            raise NotFound(msg)
        return Response(data)


class AdminNaviPortView(APIView):
    """Staff maintenance toggle for a port (accepting_orders/status_message)."""

    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        port = get_object_or_404(NaviPort, pk=pk)
        serializer = NaviPortAvailabilitySerializer(
            port, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        port = serializer.save(updated_by=request.user)
        return Response(build_port_status(port))
