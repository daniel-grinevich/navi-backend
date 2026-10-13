import re

from rest_framework import serializers

from navi_backend.core.api import BaseModelSerializer
from navi_backend.core.api.mixins import ReadOnlyAuditMixin
from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.menu.models import MenuItem


class NaviPortSerializer(BaseModelSerializer):
    show_only_to_admin_fields = (
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "raspberry_pi",
    )

    class Meta:
        model = NaviPort
        fields = [
            "id",
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "raspberry_pi",
            "espresso_machine",
            "longitude",
            "latitude",
            "address_line_1",
            "address_line_2",
            "address_line_3",
            "city",
            "state_or_region",
            "postal_code",
        ]


class RaspberryPiSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
    class Meta:
        model = RaspberryPi
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "mac_address",
            "ip_address",
            "location",
            "is_connected",
            "firmware_version",
            "last_seen",
        ]


class EspressoMachineSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
    class Meta:
        model = EspressoMachine
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "serial_number",
            "machine_type",
            "ip_address",
            "port",
            "is_online",
            "last_maintenance_at",
        ]


class MachineTypeSerializer(BaseModelSerializer):
    class Meta:
        model = MachineType
        fields = [
            "name",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "model_number",
            "maintenance_frequency",
            "supported_drinks",
        ]


MAC_ADDRESS_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


class DeviceSerializer(serializers.ModelSerializer):
    """Admin fleet view of a Pi (the "Device" in the admin API contract)."""

    enabled = serializers.BooleanField(source="is_connected", required=False)
    is_online = serializers.BooleanField(read_only=True)
    navi_port = serializers.SerializerMethodField()
    espresso_machine = serializers.SerializerMethodField()
    navi_port_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = RaspberryPi
        fields = [
            "id",
            "name",
            "slug",
            "mac_address",
            "location",
            "enabled",
            "is_online",
            "last_seen",
            "firmware_version",
            "is_simulated",
            "navi_port",
            "espresso_machine",
            "navi_port_id",
        ]
        read_only_fields = ["id", "slug", "last_seen", "firmware_version"]
        extra_kwargs = {"location": {"required": False}}

    def validate_mac_address(self, value):
        normalized = value.strip().lower().replace("-", ":")
        if not MAC_ADDRESS_RE.match(normalized):
            msg = "Enter a MAC address like dc:a6:32:00:00:01."
            raise serializers.ValidationError(msg)
        return normalized

    def validate_navi_port_id(self, value):
        if value is None:
            return None
        navi_port = NaviPort.objects.filter(pk=value).first()
        if navi_port is None:
            msg = "NaviPort not found."
            raise serializers.ValidationError(msg)
        return navi_port

    def _port(self, obj) -> NaviPort | None:
        # Prefetched by the viewset; .all() keeps it to one query per page.
        ports = list(obj.navi_port.all())
        return ports[0] if ports else None

    def get_navi_port(self, obj):
        port = self._port(obj)
        return {"id": port.id, "name": port.name} if port else None

    def get_espresso_machine(self, obj):
        port = self._port(obj)
        machine = port.espresso_machine if port else None
        if machine is None:
            return None
        return {
            "id": machine.id,
            "serial_number": machine.serial_number,
            "machine_type": machine.machine_type.name if machine.machine_type else None,
            "is_online": machine.is_online,
        }


class DeviceEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceEvent
        fields = ["id", "type", "message", "payload", "created_at"]


class DeviceTestOrderSerializer(serializers.Serializer):
    menu_item_id = serializers.UUIDField(required=False)

    def validate_menu_item_id(self, value):
        menu_item = MenuItem.objects.filter(pk=value, is_deleted=False).first()
        if menu_item is None:
            msg = "Menu item not found."
            raise serializers.ValidationError(msg)
        return menu_item


class NaviPortAvailabilitySerializer(serializers.ModelSerializer):
    """Staff maintenance toggle: pause a port and tell customers why."""

    status_message = serializers.CharField(
        max_length=255, allow_blank=True, allow_null=True, required=False
    )

    class Meta:
        model = NaviPort
        fields = ["accepting_orders", "status_message"]

    def validate_status_message(self, value):
        # The column is non-null; null in the API means "no message".
        return value or ""
