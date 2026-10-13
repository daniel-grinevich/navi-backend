from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from navi_backend.devices.services.fleet import pi_group


def broadcast_order_status(order_id, status, error=None):
    channel_layer = get_channel_layer()
    payload = {"type": "order.status.update", "status": status}
    if error:
        payload["error"] = error
    async_to_sync(channel_layer.group_send)(f"order_{order_id}", payload)


def notify_port_queue_changed(navi_port):
    """Nudge the Pi at ``navi_port`` to refetch its queue (notify-then-fetch).

    Only that port's Pi is told: other Pis never see this port's orders, so
    they have nothing to refetch.
    """
    if navi_port is None or navi_port.raspberry_pi_id is None:
        return
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        pi_group(navi_port.raspberry_pi_id), {"type": "machine.queue.changed"}
    )
