from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from navi_backend.devices.consumers import MACHINES_GROUP


def broadcast_order_status(order_id, status, error=None):
    channel_layer = get_channel_layer()
    payload = {"type": "order.status.update", "status": status}
    if error:
        payload["error"] = error
    async_to_sync(channel_layer.group_send)(f"order_{order_id}", payload)


def notify_machines_queue_changed():
    """Nudge every connected Pi to refetch its queue (notify-then-fetch)."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        MACHINES_GROUP, {"type": "machine.queue.changed"}
    )
