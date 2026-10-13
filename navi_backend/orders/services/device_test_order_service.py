"""Staff test orders: a $0 order queued at one device's NaviPort.

Lets an admin exercise the whole scan -> claim -> brew -> complete loop on a
real or simulated Pi without a customer, a card, or Stripe. The machine views
skip charging, invoicing, and awards for ``is_test`` orders.
"""

import uuid
from decimal import Decimal

from django.db import transaction

from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services.events import record_event
from navi_backend.menu.models import MenuItem
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderItem
from navi_backend.orders.utils import notify_machines_queue_changed


class DeviceNotReadyError(Exception):
    """The device can't take a test order (not attached, disabled, ...)."""


def default_test_menu_item() -> MenuItem | None:
    return (
        MenuItem.objects.filter(status=MenuItem.Status.ACTIVE, is_deleted=False)
        .order_by("name")
        .first()
    )


@transaction.atomic
def create_test_order(
    *, device: RaspberryPi, actor, menu_item: MenuItem | None = None
) -> Order:
    navi_port = device.navi_port.first()
    if navi_port is None:
        msg = "Device is not attached to a NaviPort."
        raise DeviceNotReadyError(msg)
    if not device.is_connected:
        msg = "Device is disabled; enable it before sending a test order."
        raise DeviceNotReadyError(msg)

    menu_item = menu_item or default_test_menu_item()
    order = Order.objects.create(
        user=actor,
        navi_port=navi_port,
        is_test=True,
        cart_token=f"test-order-{uuid.uuid4().hex}",
        created_by=actor,
        updated_by=actor,
    )
    if menu_item is not None:
        OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            quantity=1,
            unit_price=Decimal("0.00"),
            created_by=actor,
            updated_by=actor,
        )

    record_event(
        device.pk,
        DeviceEvent.Type.TEST_ORDER,
        message=f"Test order queued by {actor}",
        payload={
            "order_id": str(order.id),
            "menu_item": menu_item.name if menu_item else None,
        },
        actor=actor,
    )
    transaction.on_commit(notify_machines_queue_changed)
    return order
