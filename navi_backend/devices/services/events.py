"""Writing to the device event log and keeping presence fresh."""

from typing import Any

from django.core.cache import cache
from django.utils import timezone

from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.models import RaspberryPi

# Store at most one heartbeat event per Pi per window. Presence itself comes
# from last_seen (updated on every check-in); the sampled rows just give the
# event log a visible pulse without a row per 15s ping.
HEARTBEAT_SAMPLE_SECONDS = 60 * 10


def record_event(
    pi_id,
    event_type: str,
    message: str = "",
    payload: dict[str, Any] | None = None,
    actor=None,
) -> DeviceEvent:
    return DeviceEvent.objects.create(
        raspberry_pi_id=pi_id,
        type=event_type,
        message=message[:255],
        payload=payload or {},
        actor=actor,
    )


def touch_presence(pi_id, firmware_version: str | None = None) -> None:
    """Mark a Pi as seen now and record a sampled heartbeat.

    Uses a queryset ``update()`` so admin saves can't fake presence and no
    model save() side effects run on the hot path.
    """
    fields: dict[str, Any] = {"last_seen": timezone.now()}
    if firmware_version:
        fields["firmware_version"] = firmware_version[:50]
    RaspberryPi.objects.filter(pk=pi_id).update(**fields)

    # cache.add is atomic in Redis: only the first check-in per window wins.
    if cache.add(f"devices:heartbeat:{pi_id}", 1, timeout=HEARTBEAT_SAMPLE_SECONDS):
        record_event(pi_id, DeviceEvent.Type.HEARTBEAT)
