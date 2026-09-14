"""Websocket consumer for NaviPort Pis.

Field Pis sit behind café NAT, so the backend never connects to them — a Pi
always dials *out*, authenticates with its device token, and holds the socket
open. The socket carries no order payloads: the backend pushes a tiny
``queue.changed`` nudge and the Pi refetches its queue over HTTP, which stays
the single source of truth. Pings (and the connect itself) refresh
``last_seen`` so presence is real; HTTP polling remains a fallback transport.
"""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from navi_backend.devices.models import RaspberryPi

MACHINES_GROUP = "machines"


@database_sync_to_async
def _authenticate(token):
    if not token:
        return None
    return RaspberryPi.objects.filter(device_token=token, is_connected=True).first()


@database_sync_to_async
def _touch(pi_id):
    RaspberryPi.objects.filter(pk=pi_id).update(last_seen=timezone.now())


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
        await self.channel_layer.group_add(f"pi_{self.pi_id}", self.channel_name)
        await self.accept()
        await _touch(self.pi_id)
        await self.send(text_data=json.dumps({"type": "connected"}))

    async def disconnect(self, code):
        if not hasattr(self, "pi_id"):
            return
        await self.channel_layer.group_discard(MACHINES_GROUP, self.channel_name)
        await self.channel_layer.group_discard(f"pi_{self.pi_id}", self.channel_name)
        await _touch(self.pi_id)

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
