from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_order_status(order_id, status, error=None):
    channel_layer = get_channel_layer()
    payload = {"type": "order.status.update", "status": status}
    if error:
        payload["error"] = error
    async_to_sync(channel_layer.group_send)(f"order_{order_id}", payload)
