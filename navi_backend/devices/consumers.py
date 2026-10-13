"""Websocket consumer for NaviPort Pis.

Field Pis sit behind café NAT, so the backend never connects to them — a Pi
always dials *out*, authenticates with its device token, and holds the socket
open. The socket carries no order payloads: the backend pushes a tiny
``queue.changed`` nudge and the Pi refetches its queue over HTTP, which stays
the single source of truth. Pings (and the connect itself) refresh
``last_seen`` so presence is real; HTTP polling remains a fallback transport.
Connects/disconnects land in the device event log; rotating a Pi's token or
disabling it closes its socket (``machine.revoke``).
"""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services.events import record_event
from navi_backend.devices.services.events import touch_presence
from navi_backend.devices.services.fleet import pi_group

MACHINES_GROUP = "machines"

# Close code sent when the backend revokes a socket (token rotated / disabled).
REVOKED_CLOSE_CODE = 4001


@database_sync_to_async
def _authenticate(token):
    return RaspberryPi.objects.authenticate(token)


@database_sync_to_async
def _touch(pi_id, firmware_version=None):
    touch_presence(pi_id, firmware_version=firmware_version)


@database_sync_to_async
def _record(pi_id, event_type, message=""):
    record_event(pi_id, event_type, message=message)


class MachineConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        headers = dict(self.scope.get("headers") or [])
        token = headers.get(b"x-device-token", b"").decode()
        pi = await _authenticate(token)
        if pi is None:
            await self.close()
            return

        self.pi_id = pi.pk
        await self.channel_layer.group_add(MACHINES_GROUP, self.channel_name)
        await self.channel_layer.group_add(pi_group(self.pi_id), self.channel_name)
        await self.accept()
        await _record(self.pi_id, DeviceEvent.Type.CONNECTED, "Websocket connected")
        firmware = headers.get(b"x-firmware-version", b"").decode() or None
        await _touch(self.pi_id, firmware)
        await self.send(text_data=json.dumps({"type": "connected"}))

    async def disconnect(self, code):
        if not hasattr(self, "pi_id"):
            return
        await self.channel_layer.group_discard(MACHINES_GROUP, self.channel_name)
        await self.channel_layer.group_discard(pi_group(self.pi_id), self.channel_name)
        await _touch(self.pi_id)
        await _record(
            self.pi_id,
            DeviceEvent.Type.DISCONNECTED,
            f"Websocket disconnected (code {code})",
        )

    async def receive(self, text_data=None, bytes_data=None):
        try:
            message = json.loads(text_data or "")
        except json.JSONDecodeError:
            return
        if message.get("type") == "ping":
            await _touch(self.pi_id)
            await self.send(text_data=json.dumps({"type": "pong"}))

    async def machine_queue_changed(self, event):
        await self.send(text_data=json.dumps({"type": "queue.changed"}))

    async def machine_revoke(self, event):
        await self.close(code=REVOKED_CLOSE_CODE)
