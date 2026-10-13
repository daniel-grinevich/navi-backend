"""Customer-facing NaviPort status ("which machine am I at" deep link).

The sticker QR on a machine opens ``{FRONTEND_URL}/p/<slug>``; the frontend
calls ``GET /api/navi_ports/by-slug/<slug>/`` which is served from here.
Also home to the availability guards used at order create and at scan.
"""

from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from rest_framework.exceptions import ValidationError

from navi_backend.core.cache import bump_version
from navi_backend.core.cache import get_or_set_safe
from navi_backend.core.cache import versioned_key
from navi_backend.devices.models import NaviPort
from navi_backend.menu.models import MenuItem

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import QuerySet

PORT_STATUS_CACHE_NAMESPACE = "navi_port_status"
# Short: queue length and Pi presence change constantly and aren't signalled,
# so this only absorbs bursts (a crowd scanning the same sticker).
PORT_STATUS_CACHE_TTL = 10
PORT_STATUS_STALE_GRACE = 5

# Orders that are waiting for, or being made by, a port's machine.
QUEUED_ORDER_STATUSES = ("O", "S")

PORT_PAUSED_MESSAGE = "This machine isn't taking orders right now"


def invalidate_port_status_cache() -> None:
    """Orphan every cached port status (any port/machine/menu change)."""
    bump_version(PORT_STATUS_CACHE_NAMESPACE)


def get_port_status_by_slug(slug: str) -> dict[str, Any] | None:
    """Cached public status for the port with ``slug``, or None if unknown.

    Unknown slugs are cached too (as None) so a bogus sticker can't be used to
    hammer the database.
    """
    return get_or_set_safe(
        versioned_key(PORT_STATUS_CACHE_NAMESPACE, slug),
        lambda: _status_for_slug(slug),
        PORT_STATUS_CACHE_TTL,
        stale_grace=PORT_STATUS_STALE_GRACE,
    )


def _status_for_slug(slug: str) -> dict[str, Any] | None:
    port = _port_queryset().filter(slug=slug).first()
    if port is None:
        return None
    return build_port_status(port)


def _port_queryset() -> QuerySet[NaviPort]:
    return NaviPort.objects.select_related(
        "raspberry_pi", "espresso_machine__machine_type"
    )


def build_port_status(port: NaviPort) -> dict[str, Any]:
    """Serialize ``port`` into the deep-link contract (uncached)."""
    accepting = port.is_accepting_orders
    queue_length = queue_length_for(port)
    return {
        "id": str(port.id),
        "slug": port.slug,
        "name": port.name,
        "address": {
            "line1": port.address_line_1,
            "city": port.city,
            "state": port.state_or_region,
            "postal_code": port.postal_code,
        },
        "is_online": port.is_online,
        "accepting_orders": accepting,
        "status_message": None if accepting else (port.status_message or None),
        "queue_length": queue_length,
        "est_wait_seconds": queue_length * settings.NAVI_PORT_SECONDS_PER_DRINK,
        "menu_item_ids": _menu_item_ids(port),
    }


def queue_length_for(port: NaviPort) -> int:
    """Orders awaiting pickup or being made at ``port``."""
    from navi_backend.orders.models import Order  # noqa: PLC0415 - orders -> devices

    return Order.objects.filter(
        navi_port=port, order_status__in=QUEUED_ORDER_STATUSES
    ).count()


def supported_menu_items(port: NaviPort) -> QuerySet[MenuItem] | None:
    """Active MenuItems ``port``'s machine can make, or None if unrestricted.

    Unrestricted means no machine, no machine type, or a machine type with no
    ``supported_drinks`` configured.
    """
    machine = port.espresso_machine
    machine_type = machine.machine_type if machine else None
    if machine_type is None or not machine_type.supported_drinks.exists():
        return None
    return MenuItem.objects.active().filter(machinetype=machine_type)


def _menu_item_ids(port: NaviPort) -> list[str] | None:
    items = supported_menu_items(port)
    if items is None:
        return None
    return [str(pk) for pk in items.order_by("name").values_list("pk", flat=True)]


def ensure_port_accepting_orders(port: NaviPort) -> None:
    """Raise a 400 ``{"navi_port": [...]}`` if ``port`` can't take orders now."""
    if not port.is_accepting_orders:
        raise ValidationError({"navi_port": [PORT_PAUSED_MESSAGE]})


def ensure_port_supports_items(port: NaviPort, menu_items: Iterable[MenuItem]) -> None:
    """Raise a 400 ``{"items": [...]}`` for drinks ``port`` can't make."""
    supported = supported_menu_items(port)
    if supported is None:
        return
    supported_ids = set(supported.values_list("pk", flat=True))
    unsupported = [item for item in menu_items if item.pk not in supported_ids]
    if unsupported:
        names = ", ".join(sorted({item.name for item in unsupported}))
        raise ValidationError({"items": [f"This machine can't make: {names}"]})
