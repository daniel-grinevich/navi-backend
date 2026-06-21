import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from navi_backend.orders.models import Order


@database_sync_to_async
def _get_order_for_user(order_id, user):
    try:
        if user.is_staff:
            return Order.objects.get(pk=order_id)
        return Order.objects.get(pk=order_id, user=user)
    except Order.DoesNotExist:
        return None


class OrderStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        user = self.scope.get("user", AnonymousUser())

        if isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close()
            return

        order = await _get_order_for_user(self.order_id, user)
        if not order:
            await self.close()
            return

        self.group_name = f"order_{self.order_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send current status immediately so reconnects get the right state
        await self.send(text_data=json.dumps({"status": order.order_status}))

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_status_update(self, event):
        payload = {"status": event["status"]}
        if "error" in event:
            payload["error"] = event["error"]
        await self.send(text_data=json.dumps(payload))
