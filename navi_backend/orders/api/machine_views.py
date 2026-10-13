from datetime import timedelta

import stripe
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.awards.tasks import process_order_awards
from navi_backend.core.permissions import IsMachineAuthenticated
from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.services.events import record_event
from navi_backend.devices.services.port_status import PORT_PAUSED_MESSAGE
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.models import Order
from navi_backend.orders.qr import InvalidQrTokenError
from navi_backend.orders.qr import read_qr_token
from navi_backend.orders.qr import rotate_qr_nonce
from navi_backend.orders.tasks import create_order_invoice
from navi_backend.orders.utils import broadcast_order_status
from navi_backend.orders.utils import notify_port_queue_changed
from navi_backend.payments.services import StripePaymentService

from .serializers import MachineOrderSerializer

# How long a Pi's claim on an order stays exclusive. If the Pi crashes mid-drink
# the order sits in "S" forever otherwise; after this window another Pi (or the
# same one retrying) may reclaim it.
CLAIM_LEASE_SECONDS = 60 * 5


def _claim_order(order_id, raspberry_pi, navi_port):
    """Atomically move an order O -> S and stamp the claiming Pi.

    Returns the number of rows updated: 1 if this Pi won the claim, 0 if the
    order was already taken (by another Pi, or a still-fresh claim). The single
    conditional UPDATE is the lock -- the database guarantees exactly one winner
    even if two Pis scan the same QR at the same instant.
    """
    now = timezone.now()
    lease_cutoff = now - timedelta(seconds=CLAIM_LEASE_SECONDS)

    # Claimable if awaiting pickup, or held under a claim that has gone stale.
    claimable = Q(order_status="O") | Q(order_status="S", claimed_at__lt=lease_cutoff)
    # Only the Pi at the order's own NaviPort may take it.
    port_ok = Q(navi_port=navi_port)

    return Order.objects.filter(Q(pk=order_id) & claimable & port_ok).update(
        order_status="S",
        navi_port=navi_port,
        claimed_by=raspberry_pi,
        claimed_at=now,
    )


def _navi_port_for(request):
    """Return the NaviPort attached to the authenticated Pi, or None."""
    return request.raspberry_pi.navi_port.first()


class MachineOrderQueueView(APIView):
    """Orders this Pi should be aware of: pending pickups + its own in-progress.

    The Pi polls this to build its queue UI. Includes orders awaiting pickup at
    this Pi's port and orders this Pi currently holds, so a reconnecting Pi
    recovers what it was working on. Other ports' orders (and unrouted ones)
    are never listed.
    """

    permission_classes = [IsMachineAuthenticated]

    def get(self, request):
        navi_port = _navi_port_for(request)
        if not navi_port:
            return Response(
                {"detail": "Machine has no associated NaviPort."}, status=400
            )

        pending = Q(order_status="O", navi_port=navi_port)
        mine_in_progress = Q(order_status="S", claimed_by=request.raspberry_pi)

        orders = (
            Order.objects.filter(pending | mine_in_progress)
            .prefetch_related(
                "items__menu_item", "items__customizations__customization"
            )
            .order_by("created_at")
        )
        serializer = MachineOrderSerializer(orders, many=True)
        return Response(serializer.data)


class MachineOrderScanView(APIView):
    """The Pi scans a QR: verify the signed token, then atomically claim.

    This is the primary pickup entry point. The QR carries an opaque signed
    token (never the raw order id); we verify it here and hand off to the same
    atomic claim used by the start endpoint.
    """

    permission_classes = [IsMachineAuthenticated]

    def post(self, request):
        token = request.data.get("qr_token")
        if not token:
            return Response({"detail": "qr_token is required."}, status=400)

        try:
            order_id = read_qr_token(token)
        except InvalidQrTokenError as exc:
            return Response({"detail": str(exc)}, status=400)

        return _start_order(request, order_id)


class MachineOrderStartView(APIView):
    """Claim an order by id (direct/testing path; QR path uses /scan/)."""

    permission_classes = [IsMachineAuthenticated]

    def post(self, request, order_id):
        return _start_order(request, order_id)


def _port_paused_response(navi_port):
    """409 if staff paused this port, else None.

    Single guard so the scan rewrite (J7) can keep it as one call.
    """
    if navi_port.accepting_orders:
        return None
    return Response(
        {
            "detail": PORT_PAUSED_MESSAGE,
            "code": "port_paused",
            "status_message": navi_port.status_message or None,
        },
        status=409,
    )


def _start_order(request, order_id):
    navi_port = _navi_port_for(request)
    if not navi_port:
        return Response({"detail": "Machine has no associated NaviPort."}, status=400)

    paused = _port_paused_response(navi_port)
    if paused:
        return paused

    order = get_object_or_404(Order, pk=order_id)

    if order.navi_port_id != navi_port.pk:
        return Response(
            {"detail": "This order is assigned to a different location."},
            status=400,
        )

    claimed = _claim_order(order_id, request.raspberry_pi, navi_port)
    if not claimed:
        # Lost the race, or the order is in a terminal state (done/cancelled).
        order.refresh_from_db()
        return Response(
            {
                "detail": "Order is not available to start.",
                "order_status": order.order_status,
            },
            status=409,
        )

    # The QR that was just scanned is spent; any copy of it is now dead.
    rotate_qr_nonce(order_id)

    # We won the claim, so the order now carries this port -> its tax
    # jurisdiction. Charge the saved card before making the drink; if the charge
    # is declined, release the claim so nothing is dispensed for free. Staff
    # test orders are $0 and never touch Stripe.
    order.refresh_from_db()
    try:
        if not order.is_test:
            StripePaymentService.charge_order(order)
    except (stripe.error.StripeError, ValueError) as exc:
        Order.objects.filter(pk=order_id, claimed_by=request.raspberry_pi).update(
            order_status="O", claimed_by=None, claimed_at=None
        )
        rotate_qr_nonce(order_id)
        # Order is back in the queue for another attempt; let the Pi know.
        notify_port_queue_changed(navi_port)
        return Response(
            {"detail": "Payment could not be completed.", "error": str(exc)},
            status=402,
        )

    order.refresh_from_db()
    record_event(
        request.raspberry_pi.pk,
        DeviceEvent.Type.ORDER_CLAIMED,
        message=f"Claimed order {order.id}",
        payload=_order_payload(order),
    )
    broadcast_order_status(order.id, "S")
    notify_port_queue_changed(navi_port)
    return Response(MachineOrderSerializer(order).data)


def _order_payload(order, **extra):
    return {"order_id": str(order.id), "is_test": order.is_test, **extra}


class MachineOrderCompleteView(APIView):
    permission_classes = [IsMachineAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        outcome = request.data.get("outcome")
        error_message = request.data.get("error_message", "")
        if outcome not in ("complete", "error"):
            return Response(
                {"detail": "outcome must be 'complete' or 'error'."}, status=400
            )

        # Mirror of _claim_order: one conditional UPDATE both verifies this Pi
        # still holds the claim and releases it, so a stale Pi racing a reclaim
        # can't finish an order it no longer owns.
        new_status = "D" if outcome == "complete" else "O"
        updated = Order.objects.filter(
            pk=order_id,
            order_status="S",
            claimed_by=request.raspberry_pi,
        ).update(order_status=new_status, claimed_by=None, claimed_at=None)
        if not updated:
            return Response(
                {"detail": "Order is not claimed by this machine."}, status=409
            )
        rotate_qr_nonce(order_id)

        if outcome == "complete":
            # Payment was already taken at scan (start), so completion just
            # finalizes the order and kicks off invoicing + awards.
            record_event(
                request.raspberry_pi.pk,
                DeviceEvent.Type.BREW_COMPLETED,
                message=f"Completed order {order.id}",
                payload=_order_payload(order),
            )
            broadcast_order_status(order.id, "D")
            if not order.is_test:
                create_order_invoice.apply_async(args=[order.id])
                process_order_awards.apply_async(args=[str(order.id)])
        else:
            record_event(
                request.raspberry_pi.pk,
                DeviceEvent.Type.BREW_FAILED,
                message=error_message or f"Brew failed for order {order.id}",
                payload=_order_payload(order, error_message=error_message),
            )
            MachineErrorLog.objects.create(
                order=order,
                raspberry_pi=request.raspberry_pi,
                error_message=error_message,
            )
            broadcast_order_status(order.id, "O", error=error_message)

        notify_port_queue_changed(order.navi_port)
        return Response({"ok": True})
