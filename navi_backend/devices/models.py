from django.db import models
from django.utils.translation import gettext_lazy as _

from navi_backend.core.models import AddressModel
from navi_backend.core.models import AuditModel
from navi_backend.core.models import NamedModel
from navi_backend.core.models import SlugifiedModel
from navi_backend.menu.models import MenuItem


class RaspberryPi(
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    mac_address = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True)
    is_connected = models.BooleanField(default=False)
    firmware_version = models.CharField(max_length=50, blank=True)
    last_seen = models.DateTimeField(auto_now=True)


class MachineType(
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    model_number = models.CharField(max_length=100)
    maintenance_frequency = models.IntegerField(
        help_text="Required Maintenance Frequency in Days"
    )
    supported_drinks = models.ManyToManyField(MenuItem, blank=True)


class EspressoMachine(
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    serial_number = models.CharField(max_length=100, unique=True)
    machine_type = models.ForeignKey(
        MachineType,
        verbose_name=_("Machine Type"),
        related_name="espresso_machine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Espresso Machine type"),
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    port = models.IntegerField(blank=True, null=True)
    is_online = models.BooleanField(default=False)
    last_maintenance_at = models.DateTimeField(blank=True, null=True)


class NaviPort(SlugifiedModel, NamedModel, AuditModel, AddressModel):
    espresso_machine = models.ForeignKey(
        EspressoMachine,
        verbose_name=_("Espresso Machine"),
        related_name="navi_port",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Espresso Machine attached to this NaviPort"),
    )
    raspberry_pi = models.ForeignKey(
        RaspberryPi,
        verbose_name=_("Raspberry Pi"),
        related_name="navi_port",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Raspberry Pi attached to this NaviPort"),
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True)

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)
