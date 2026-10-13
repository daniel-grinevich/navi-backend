from django.db.models import Prefetch
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from navi_backend.core.api.mixins.track_user_mixin import TrackUserMixin
from navi_backend.core.pagination import StandardResultsSetPagination
from navi_backend.core.permissions import IsAdminUserOrReadOnly
from navi_backend.devices.api.serializers import DeviceEventSerializer
from navi_backend.devices.api.serializers import DeviceSerializer
from navi_backend.devices.api.serializers import DeviceTestOrderSerializer
from navi_backend.devices.api.serializers import EspressoMachineSerializer
from navi_backend.devices.api.serializers import MachineTypeSerializer
from navi_backend.devices.api.serializers import NaviPortSerializer
from navi_backend.devices.api.serializers import RaspberryPiSerializer
from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services import fleet
from navi_backend.orders.qr import make_qr_token
from navi_backend.orders.services.device_test_order_service import DeviceNotReadyError
from navi_backend.orders.services.device_test_order_service import create_test_order

DEFAULT_EVENT_LIMIT = 50
MAX_EVENT_LIMIT = 200


class DeviceNotReady(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "device_not_ready"


class NaviPortViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = NaviPort.objects.select_related("espresso_machine", "raspberry_pi")
    serializer_class = NaviPortSerializer
    permission_classes = [IsAdminUserOrReadOnly]


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


class AdminDeviceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Staff-only provisioning for the Pi fleet: create, enable/disable,
    attach to a NaviPort, rotate tokens, inspect events, send test orders.

    Devices are disabled rather than deleted, so their event history and order
    claims survive.
    """

    serializer_class = DeviceSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = RaspberryPi.objects.prefetch_related(
            Prefetch(
                "navi_port",
                queryset=NaviPort.objects.select_related(
                    "espresso_machine__machine_type"
                ),
            )
        ).order_by("name")
        if self.action != "list":
            return qs

        params = self.request.query_params
        is_online = params.get("is_online", "").lower()
        if is_online in ("true", "1"):
            qs = qs.online()
        elif is_online in ("false", "0"):
            qs = qs.offline()
        search = params.get("search", "").strip()
        if search:
            qs = qs.search(search)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        navi_port = data.pop("navi_port_id", None)
        # A freshly provisioned device should work as soon as it's flashed.
        data.setdefault("is_connected", True)

        pi, token = fleet.create_device(
            actor=request.user, data=data, navi_port=navi_port
        )
        body = {**self.get_serializer(self.get_queryset().get(pk=pi.pk)).data}
        body["device_token"] = token
        return Response(body, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        pi = self.get_object()
        serializer = self.get_serializer(
            pi, data=request.data, partial=kwargs.get("partial", False)
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        set_navi_port = "navi_port_id" in data
        navi_port = data.pop("navi_port_id", None)

        fleet.update_device(
            pi,
            actor=request.user,
            data=data,
            navi_port=navi_port,
            set_navi_port=set_navi_port,
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=pi.pk)).data)

    @action(detail=True, methods=["post"], url_path="rotate-token")
    def rotate_token(self, request, pk=None):
        token = fleet.rotate_token(self.get_object(), actor=request.user)
        return Response({"device_token": token})

    @action(detail=True, methods=["post"], url_path="test-order")
    def test_order(self, request, pk=None):
        pi = self.get_object()
        serializer = DeviceTestOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = create_test_order(
                device=pi,
                actor=request.user,
                menu_item=serializer.validated_data.get("menu_item_id"),
            )
        except DeviceNotReadyError as exc:
            raise DeviceNotReady(str(exc)) from exc
        return Response(
            {"order_id": order.id, "qr_token": make_qr_token(order)},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        pi = self.get_object()
        limit = _parse_limit(request.query_params.get("limit"))
        events = pi.events.order_by("-created_at")[:limit]
        return Response({"results": DeviceEventSerializer(events, many=True).data})


def _parse_limit(raw) -> int:
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_EVENT_LIMIT
    return max(1, min(limit, MAX_EVENT_LIMIT))
