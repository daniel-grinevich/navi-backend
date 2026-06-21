from django.urls import path

from navi_backend.orders.consumers import OrderStatusConsumer

websocket_urlpatterns = [
    path("ws/orders/<str:order_id>/", OrderStatusConsumer.as_asgi()),
]
