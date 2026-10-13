"""Machine reported an ``error`` outcome: cancel the order and refund it.

Product decision: a failed brew is never put back in the queue (that is how a
rescan used to charge twice). The order is cancelled with the machine's reason
and, if the card was charged, the full amount is refunded straight away. The
customer reorders if they still want a drink.

The cancel is committed before Stripe is called. If the refund call fails the
order stays cancelled with a succeeded payment, and a Celery task retries the
refund (same idempotency key, so it can't refund twice); staff can also use the
admin refund endpoint.
"""

import stripe
from django.db import transaction

from navi_backend.core.logging import get_logger
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.models import Order
from navi_backend.orders.models import Status
from navi_backend.orders.qr import rotate_qr_nonce
from navi_backend.orders.services.refund_order_service import RefundError
from navi_backend.orders.services.refund_order_service import RefundOrderService
from navi_backend.orders.tasks import refund_order
from navi_backend.orders.utils import broadcast_order_status
from navi_backend.orders.utils import notify_port_queue_changed

logger = get_logger(__name__)


class OrderNotClaimedError(Exception):
    pass


def machine_error_reason(error_message):
    return f"Machine error: {error_message}" if error_message else "Machine error"


def fail_order(order, raspberry_pi, error_message):
    """Cancel ``order`` (held by ``raspberry_pi``) and refund any charge.

    Returns True if the order was refunded now. Raises
    ``OrderNotClaimedError`` if this Pi doesn't hold the order.
    """
    reason = machine_error_reason(error_message)

    with transaction.atomic():
        # Mirror of claim_order: one conditional UPDATE both verifies this Pi
        # still holds the claim and releases it, so a stale Pi racing a reclaim
        # can't fail an order it no longer owns.
        updated = Order.objects.filter(
            pk=order.pk,
            order_status=Status.SENT,
            claimed_by=raspberry_pi,
        ).update(
            order_status=Status.CANCELLED,
            cancel_reason=reason,
            claimed_by=None,
            claimed_at=None,
        )
        if not updated:
            raise OrderNotClaimedError
        rotate_qr_nonce(order.pk)
        MachineErrorLog.objects.create(
            order=order,
            raspberry_pi=raspberry_pi,
            error_message=error_message,
        )

    transaction.on_commit(
        lambda: broadcast_order_status(order.id, "C", error=error_message),
        robust=True,
    )
    transaction.on_commit(
        lambda: notify_port_queue_changed(order.navi_port), robust=True
    )

    return _refund_after_failure(order, reason)


def _refund_after_failure(order, reason):
    try:
        RefundOrderService.refund(order.pk, reason, notify=False)
    except RefundError:
        # Nothing was charged (or it's already refunded): nothing to give back.
        return False
    except stripe.error.StripeError:
        logger.exception("machine_error_refund_failed", order_id=order.id)
        order_id = str(order.pk)
        transaction.on_commit(
            lambda: refund_order.apply_async(args=[order_id, reason]), robust=True
        )
        return False
    return True
