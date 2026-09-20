"""Tests for the machine (Raspberry Pi) websocket consumer.

Covers device-token auth, presence (last_seen touch on connect/ping), the
queue.changed nudge, and the asgi routing that lets non-browser device clients
connect without an Origin header.
"""

import pytest
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from navi_backend.devices.consumers import MachineConsumer
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.orders.utils import notify_machines_queue_changed

pytestmark = pytest.mark.django_db(transaction=True)


@database_sync_to_async
def _make_pi(**kwargs):
    kwargs.setdefault("is_connected", True)
    kwargs.setdefault("last_seen", None)
    return RaspberryPiFactory(**kwargs)


@database_sync_to_async
def _last_seen(pi):
    return RaspberryPi.objects.get(pk=pi.pk).last_seen


def _communicator(token=None, application=None):
    headers = [(b"host", b"testserver")]
    if token is not None:
        headers.append((b"x-device-token", token.encode()))
    return WebsocketCommunicator(
        application or MachineConsumer.as_asgi(), "/ws/machine/", headers=headers
    )


class TestMachineConsumerAuth:
    async def test_rejects_missing_token(self):
        communicator = _communicator()
        connected, _ = await communicator.connect()
        assert not connected

    async def test_rejects_bad_token(self):
        await _make_pi()
        communicator = _communicator("wrong-token")
        connected, _ = await communicator.connect()
        assert not connected

    async def test_rejects_disabled_pi(self):
        pi = await _make_pi(is_connected=False)
        communicator = _communicator(pi.device_token)
        connected, _ = await communicator.connect()
        assert not connected


class TestMachineConsumer:
    async def test_connect_sets_presence(self):
        pi = await _make_pi()
        communicator = _communicator(pi.device_token)
        connected, _ = await communicator.connect()
        assert connected

        assert await communicator.receive_json_from() == {"type": "connected"}
        assert await _last_seen(pi) is not None
        await communicator.disconnect()

    async def test_ping_pong_touches_last_seen(self):
        pi = await _make_pi()
        communicator = _communicator(pi.device_token)
        await communicator.connect()
        await communicator.receive_json_from()  # connected

        first_seen = await _last_seen(pi)
        await communicator.send_json_to({"type": "ping"})
        assert await communicator.receive_json_from() == {"type": "pong"}
        assert await _last_seen(pi) >= first_seen
        await communicator.disconnect()

    async def test_queue_changed_nudge_reaches_pi(self):
        pi = await _make_pi()
        communicator = _communicator(pi.device_token)
        await communicator.connect()
        await communicator.receive_json_from()  # connected

        # The sync util used by views/services; run it off the event loop.
        await sync_to_async(notify_machines_queue_changed, thread_sensitive=False)()
        assert await communicator.receive_json_from() == {"type": "queue.changed"}
        await communicator.disconnect()

    async def test_full_asgi_route_without_origin_header(self):
        """Device clients send no Origin header; the machine route must not be
        behind AllowedHostsOriginValidator (which rejects a missing Origin)."""
        from config.asgi import application  # noqa: PLC0415

        pi = await _make_pi()
        communicator = _communicator(pi.device_token, application=application)
        connected, _ = await communicator.connect()
        assert connected
        assert await communicator.receive_json_from() == {"type": "connected"}
        await communicator.disconnect()
