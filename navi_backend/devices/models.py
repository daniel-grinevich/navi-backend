import secrets

from django.db import models
from django.utils.translation import gettext_lazy as _

from navi_backend.core.models import AddressModel
from navi_backend.core.models import AuditModel
from navi_backend.core.models import NamedModel
from navi_backend.core.models import SlugifiedModel
from navi_backend.core.models import UUIDModel
from navi_backend.devices.managers import DeviceEventQuerySet
from navi_backend.devices.managers import RaspberryPiQuerySet
from navi_backend.devices.managers import hash_device_token
from navi_backend.devices.managers import online_cutoff
from navi_backend.menu.models import MenuItem
from navi_backend.users.models import User


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
    # SHA-256 of the device token. The plaintext is shown once (on create or
    # rotation) and never stored, so a DB leak can't impersonate a Pi.
    token_hash = models.CharField(
        max_length=64, unique=True, null=True, blank=True, editable=False
    )
    is_simulated = models.BooleanField(
        default=False, help_text=_("A local/QEMU simulator rather than real hardware.")
    )

    objects = RaspberryPiQuerySet.as_manager()

    def issue_token(self) -> str:
        """Replace this Pi's token and return the new plaintext (unsaved).

        Callers persist ``token_hash``; the returned plaintext is the only copy.
        """
        token = secrets.token_urlsafe(32)
        self.token_hash = hash_device_token(token)
        return token

    @property
    def is_online(self):
        if not self.last_seen:
            return False
        return self.last_seen >= online_cutoff()


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


class DeviceEvent(UUIDModel):
    """Append-only operational log for a Pi: connects, claims, brews, admin ops.

    Heartbeats are sampled (see ``devices.services.events``) rather than stored
    per ping, and ``purge_old_device_events`` trims rows past retention.
    """

    class Type(models.TextChoices):
        CONNECTED = "connected", _("Connected")
        DISCONNECTED = "disconnected", _("Disconnected")
        HEARTBEAT = "heartbeat", _("Heartbeat")
        ORDER_CLAIMED = "order_claimed", _("Order claimed")
        BREW_STARTED = "brew_started", _("Brew started")
        BREW_COMPLETED = "brew_completed", _("Brew completed")
        BREW_FAILED = "brew_failed", _("Brew failed")
        TOKEN_ROTATED = "token_rotated", _("Token rotated")
        TEST_ORDER = "test_order", _("Test order")

    raspberry_pi = models.ForeignKey(
        RaspberryPi, on_delete=models.CASCADE, related_name="events"
    )
    type = models.CharField(max_length=32, choices=Type.choices)
    message = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    # The staff user behind admin-initiated events; null for device events.
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = DeviceEventQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["raspberry_pi", "-created_at"])]

    def __str__(self):
        return f"{self.raspberry_pi_id} {self.type} @ {self.created_at:%Y-%m-%d %H:%M}"
