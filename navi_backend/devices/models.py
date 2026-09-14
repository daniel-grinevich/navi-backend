import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from navi_backend.core.models import AddressModel
from navi_backend.core.models import AuditModel
from navi_backend.core.models import NamedModel
from navi_backend.core.models import SlugifiedModel
from navi_backend.core.models import UUIDModel
from navi_backend.menu.models import MenuItem

# A Pi is "online" if it has checked in (HTTP poll or websocket ping) within
# this window. Pis ping every ~15s and poll every ~3-30s, so 60s is generous.
ONLINE_WINDOW_SECONDS = 60


class RaspberryPi(
    UUIDModel,
    SlugifiedModel,
    NamedModel,
    AuditModel,
):
    mac_address = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True)
    # Admin "enabled" switch -- machine auth requires it. NOT presence; see
    # last_seen / is_online for whether the device is actually checking in.
    is_connected = models.BooleanField(default=False)
    firmware_version = models.CharField(max_length=50, blank=True)
    # Updated via queryset .update() on every authenticated machine request and
    # websocket ping, so admin saves can't fake presence (hence no auto_now).
    last_seen = models.DateTimeField(null=True, blank=True)
    device_token = models.CharField(max_length=64, unique=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.device_token:
            self.device_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def is_online(self):
        if not self.last_seen:
            return False
        cutoff = timezone.now() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
        return self.last_seen >= cutoff


class MachineType(
    UUIDModel,
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
    UUIDModel,
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


class NaviPort(UUIDModel, SlugifiedModel, NamedModel, AuditModel, AddressModel):
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
