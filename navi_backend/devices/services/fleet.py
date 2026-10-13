"""Provisioning use-cases for the admin device-fleet API."""

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services.events import record_event


def pi_group(pi_id) -> str:
    """Channels group holding a single Pi's websocket(s)."""
    return f"pi_{pi_id}"


def disconnect_device(pi_id) -> None:
    """Drop any open websocket for this Pi so it must re-authenticate.

    HTTP requests re-check the token every call, but an already-open socket
    would otherwise outlive a rotated token or a disable.
    """
    async_to_sync(get_channel_layer().group_send)(
        pi_group(pi_id), {"type": "machine.revoke"}
    )


@transaction.atomic
def create_device(
    *, actor, data: dict[str, Any], navi_port: NaviPort | None = None
) -> tuple[RaspberryPi, str]:
    """Create a Pi and return it with its plaintext token (shown only once)."""
    pi = RaspberryPi(created_by=actor, updated_by=actor, **data)
    token = pi.issue_token()
    pi.save()
    if navi_port is not None:
        attach_navi_port(pi, navi_port, actor=actor)
    return pi, token


@transaction.atomic
def update_device(
    pi: RaspberryPi,
    *,
    actor,
    data: dict[str, Any],
    navi_port: NaviPort | None = None,
    set_navi_port: bool = False,
) -> RaspberryPi:
    was_enabled = pi.is_connected
    for field, value in data.items():
        setattr(pi, field, value)
    pi.updated_by = actor
    pi.save()

    if set_navi_port:
        attach_navi_port(pi, navi_port, actor=actor)
    if was_enabled and not pi.is_connected:
        transaction.on_commit(lambda: disconnect_device(pi.pk))
    return pi


def attach_navi_port(pi: RaspberryPi, navi_port: NaviPort | None, *, actor) -> None:
    """Make ``navi_port`` this Pi's only port (or detach it when None).

    A port holds one Pi, so attaching replaces whatever Pi it had.
    """
    pi.navi_port.exclude(pk=getattr(navi_port, "pk", None)).update(
        raspberry_pi=None, updated_by=actor
    )
    if navi_port is not None and navi_port.raspberry_pi_id != pi.pk:
        NaviPort.objects.filter(pk=navi_port.pk).update(
            raspberry_pi=pi, updated_by=actor
        )


@transaction.atomic
def rotate_token(pi: RaspberryPi, *, actor) -> str:
    """Issue a new token; the old one stops working as soon as this commits."""
    token = pi.issue_token()
    pi.updated_by = actor
    pi.save(update_fields=["token_hash", "updated_by", "updated_at"])
    record_event(
        pi.pk,
        DeviceEvent.Type.TOKEN_ROTATED,
        message=f"Token rotated by {actor}",
        actor=actor,
    )
    transaction.on_commit(lambda: disconnect_device(pi.pk))
    return token
