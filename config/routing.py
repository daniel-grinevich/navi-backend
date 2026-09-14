from django.urls import path

from navi_backend.devices.consumers import MachineConsumer
from navi_backend.orders.consumers import OrderStatusConsumer

# Browser-facing sockets: cookie-authenticated, origin-validated in asgi.py.
websocket_urlpatterns = [
    path("ws/orders/<str:order_id>/", OrderStatusConsumer.as_asgi()),
]

# Device sockets: authenticated by X-Device-Token, not cookies, so they skip
# the origin check (which exists to protect cookie auth from cross-site
# pages) -- non-browser clients send no Origin header at all.
machine_websocket_urlpatterns = [
    path("ws/machine/", MachineConsumer.as_asgi()),
]
