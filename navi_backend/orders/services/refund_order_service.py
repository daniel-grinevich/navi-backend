"""Full refunds of a charged order: machine failure or a staff decision.

Shared by the machine ``error`` outcome and the staff refund endpoint. The
Stripe Refund carries a fixed idempotency key (``order-{id}-refund``), so a
retry, a Celery re-run or a race between the two callers all resolve to the
same single Refund. The result is saved in its own transaction after Stripe
answers; nothing here runs inside a request-wide transaction.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from navi_backend.core.logging import get_logger
from navi_backend.orders.models import Order
from navi_backend.orders.models import Status
from navi_backend.orders.qr import rotate_qr_nonce
from navi_backend.orders.utils import broadcast_order_status
from navi_backend.orders.utils import notify_port_queue_changed
from navi_backend.payments.models import Payment
from navi_backend.payments.services import StripePaymentService
from navi_backend.payments.services import refund_idempotency_key

logger = get_logger(__name__)


class RefundError(Exception):
    """Base class for reasons an order can't be refunded."""


class NotChargedError(RefundError):
    pass


class AlreadyRefundedError(RefundError):
    pass


@dataclass(frozen=True)
class RefundResult:
    order_id: str
    order_status: str
    payment_status: str
    refund_id: str
    amount: Decimal


class RefundOrderService:
    @staticmethod
    def refund(order_id, reason, *, notify=True):
        """Refund the full charge on ``order_id`` and cancel the order.

        ``notify=False`` skips the customer/Pi broadcasts for a caller that
        already sent its own (the machine-failure path).

        Raises ``Order.DoesNotExist``, ``NotChargedError``,
        ``AlreadyRefundedError`` or a ``stripe.error.StripeError`` if Stripe
        refuses (nothing is changed locally in that case).
        """
        order = Order.objects.select_related("payment", "navi_port").get(pk=order_id)
        payment = order.payment
        if payment is not None and payment.status == "refunded":
            raise AlreadyRefundedError
        if payment is None or not payment.is_charged:
            raise NotChargedError

        refund = StripePaymentService.refund_payment(
            payment, idempotency_key=refund_idempotency_key(order)
        )
        amount = Decimal(refund.amount) / 100

        with transaction.atomic():
            Payment.objects.filter(pk=payment.pk).update(
                status="refunded",
                stripe_refund_id=refund.id,
                amount_refunded=amount,
            )
            Order.objects.filter(pk=order.pk).update(
                order_status=Status.CANCELLED,
                cancel_reason=reason,
                claimed_by=None,
                claimed_at=None,
            )
            rotate_qr_nonce(order.pk)

        logger.info(
            "order_refunded",
            order_id=order.id,
            refund_id=refund.id,
            amount=amount,
            reason=reason,
        )
        if notify:
            transaction.on_commit(
                lambda: broadcast_order_status(order.id, "C"), robust=True
            )
            navi_port = order.navi_port
            transaction.on_commit(
                lambda: notify_port_queue_changed(navi_port), robust=True
            )

        return RefundResult(
            order_id=str(order.id),
            order_status="C",
            payment_status="refunded",
            refund_id=refund.id,
            amount=amount,
        )
