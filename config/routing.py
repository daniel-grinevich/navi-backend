from django.urls import re_path

from navi_backend.orders.consumers import OrderStatusConsumer

websocket_urlpatterns = [
    re_path(r"ws/orders/(?P<order_id>[^/]+)/$", OrderStatusConsumer.as_asgi()),
]
