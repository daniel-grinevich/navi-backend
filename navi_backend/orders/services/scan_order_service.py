"""Scan-to-start: a Pi claims an order and the saved card is charged once.

Runs outside a request-wide transaction (the scan view is
``non_atomic_requests``) so each step commits on its own:

1. Claim the order (one conditional UPDATE, committed before Stripe is called).
2. Charge the saved card. ``charge_order`` skips the call if a succeeded
   PaymentIntent is already recorded and sends a fixed idempotency key, so a
   rescan/retry can never create a second charge.
3. The charge result is saved straight away, so a later failure in this request
   (Redis blip, serializer error) can't roll it back while the money is taken.
4. Customer broadcasts and Pi nudges go out after commit, so nobody refetches
   state that isn't saved yet.

Stuck orders: if a Pi dies mid-brew the order sits in "S" until its lease goes
stale, then a rescan may claim it again. The card was already charged, so the
reclaim makes the drink without charging again (``charge_order`` sees the
succeeded PaymentIntent). The dead Pi's abandoned claim is logged as a
MachineErrorLog so staff can spot a machine that made two drinks.
"""

from datetime import timedelta

import stripe
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from navi_backend.core.logging import get_logger
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.models import Order
from navi_backend.orders.models import Status
from navi_backend.orders.utils import broadcast_order_status
from navi_backend.orders.utils import notify_machines_queue_changed
from navi_backend.payments.services import StripePaymentService

logger = get_logger(__name__)

# How long a Pi's claim on an order stays exclusive. If the Pi crashes mid-drink
# the order sits in "S" forever otherwise; after this window another Pi (or the
# same one retrying) may reclaim it.
CLAIM_LEASE_SECONDS = 60 * 5


class ScanOrderError(Exception):
    """Base class for reasons a scanned order can't be started."""


class WrongLocationError(ScanOrderError):
    pass


class OrderNotAvailableError(ScanOrderError):
    def __init__(self, order_status):
        self.order_status = order_status
        super().__init__("Order is not available to start.")


class PaymentFailedError(ScanOrderError):
    pass


def claim_order(order_id, raspberry_pi, navi_port):
    """Atomically move an order O -> S and stamp the claiming Pi.

    Returns the number of rows updated: 1 if this Pi won the claim, 0 if the
    order was already taken (by another Pi, or a still-fresh claim). The single
    conditional UPDATE is the lock -- the database guarantees exactly one winner
    even if two Pis scan the same QR at the same instant.
    """
    now = timezone.now()
    lease_cutoff = now - timedelta(seconds=CLAIM_LEASE_SECONDS)

    # Claimable if awaiting pickup, or held under a claim that has gone stale.
    claimable = Q(order_status=Status.ORDERED) | Q(
        order_status=Status.SENT, claimed_at__lt=lease_cutoff
    )
    # An order may be pre-routed to a port, or unassigned until first scanned.
    port_ok = Q(navi_port=navi_port) | Q(navi_port__isnull=True)

    return Order.objects.filter(Q(pk=order_id) & claimable & port_ok).update(
        order_status=Status.SENT,
        navi_port=navi_port,
        claimed_by=raspberry_pi,
        claimed_at=now,
    )


def start_order(order_id, raspberry_pi, navi_port):
    """Claim ``order_id`` for ``raspberry_pi`` and charge it (once).

    Returns the claimed Order. Raises ``Order.DoesNotExist``,
    ``WrongLocationError``, ``OrderNotAvailableError`` or
    ``PaymentFailedError``.
    """
    order = Order.objects.get(pk=order_id)
    if order.navi_port_id and order.navi_port_id != navi_port.pk:
        raise WrongLocationError

    previous_status = order.order_status
    previous_pi_id = order.claimed_by_id

    with transaction.atomic():
        claimed = claim_order(order_id, raspberry_pi, navi_port)
    if not claimed:
        # Lost the race, or the order is in a terminal state (done/cancelled).
        order.refresh_from_db(fields=["order_status"])
        raise OrderNotAvailableError(order.order_status)

    # We won the claim, so the order now carries this port -> its tax
    # jurisdiction.
    order = Order.objects.select_related("payment", "navi_port", "user").get(
        pk=order_id
    )
    if previous_status == Status.SENT:
        _log_stale_reclaim(order, previous_pi_id)

    try:
        StripePaymentService.charge_order(order)
    except (stripe.error.StripeError, ValueError) as exc:
        # Declined (or no card): release the claim so nothing is dispensed
        # for free. A timeout that actually charged is safe to retry -- the
        # idempotency key returns the original PaymentIntent.
        _release_claim(order, raspberry_pi)
        raise PaymentFailedError(str(exc)) from exc

    order.refresh_from_db()
    transaction.on_commit(
        lambda: broadcast_order_status(order.id, Status.SENT), robust=True
    )
    transaction.on_commit(notify_machines_queue_changed, robust=True)
    return order


def _release_claim(order, raspberry_pi):
    with transaction.atomic():
        Order.objects.filter(pk=order.pk, claimed_by=raspberry_pi).update(
            order_status=Status.ORDERED, claimed_by=None, claimed_at=None
        )
    # Order is back in the queue for another attempt; let machines know.
    transaction.on_commit(notify_machines_queue_changed, robust=True)


def _log_stale_reclaim(order, previous_pi_id):
    logger.warning(
        "order_stale_claim_reclaimed",
        order_id=order.id,
        previous_pi_id=previous_pi_id,
        new_pi_id=order.claimed_by_id,
    )
    MachineErrorLog.objects.create(
        order=order,
        raspberry_pi_id=previous_pi_id,
        error_message=(
            "Claim lease expired without completion; order reclaimed by "
            f"another scan (Pi {order.claimed_by_id}). An existing charge is "
            "not repeated."
        ),
    )
