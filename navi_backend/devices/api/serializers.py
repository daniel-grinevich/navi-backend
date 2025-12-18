from rest_framework import serializers

from navi_backend.core.api.serializers import BaseModelSerializer
from navi_backend.core.api.serializers import ReadOnlyAuditMixin
from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi


class NaviPortSerializer(BaseModelSerializer):
    show_only_to_admin_fields = [
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "raspberry_pi",
    ]

    class Meta:
        model = NaviPort
        fields = [
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
