from datetime import timedelta

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.awards.tasks import process_order_awards
from navi_backend.core.permissions import IsMachineAuthenticated
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.models import Order
from navi_backend.orders.qr import InvalidQrTokenError
from navi_backend.orders.qr import read_qr_token
from navi_backend.orders.tasks import create_order_invoice
from navi_backend.orders.utils import broadcast_order_status
from navi_backend.payments.tasks import capture_stripe_payment

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
    # An order may be pre-routed to a port, or unassigned until first scanned.
    port_ok = Q(navi_port=navi_port) | Q(navi_port__isnull=True)

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
    this Pi's port (or not yet routed to any port) and orders this Pi currently
    holds, so a reconnecting Pi recovers what it was working on.
    """

    permission_classes = [IsMachineAuthenticated]

    def get(self, request):
        navi_port = _navi_port_for(request)
        if not navi_port:
            return Response(
                {"detail": "Machine has no associated NaviPort."}, status=400
            )

        pending = Q(order_status="O") & (
            Q(navi_port=navi_port) | Q(navi_port__isnull=True)
        )
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


def _start_order(request, order_id):
    navi_port = _navi_port_for(request)
    if not navi_port:
        return Response({"detail": "Machine has no associated NaviPort."}, status=400)

    order = get_object_or_404(Order, pk=order_id)

    if order.navi_port and order.navi_port.pk != navi_port.pk:
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

    order.refresh_from_db()
    broadcast_order_status(order.id, "S")
    return Response(MachineOrderSerializer(order).data)


class MachineOrderCompleteView(APIView):
    permission_classes = [IsMachineAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        # Only the Pi that holds the claim may complete or fail it.
        if order.claimed_by_id and order.claimed_by_id != request.raspberry_pi.id:
            return Response(
                {"detail": "Order is claimed by another machine."}, status=409
            )

        outcome = request.data.get("outcome")
        error_message = request.data.get("error_message", "")

        if outcome == "complete":
            order.order_status = "D"
            order.claimed_by = None
            order.claimed_at = None
            order.save(update_fields=["order_status", "claimed_by", "claimed_at"])
            broadcast_order_status(order.id, "D")
            capture_stripe_payment.apply_async(
                args=[order.payment.stripe_payment_intent_id],
            )
            create_order_invoice.apply_async(args=[order.id], queue="invoice")
            process_order_awards.apply_async(args=[str(order.id)])

        elif outcome == "error":
            MachineErrorLog.objects.create(
                order=order,
                raspberry_pi=request.raspberry_pi,
                error_message=error_message,
            )
            # Release the claim so the order can be picked up again.
            order.order_status = "O"
            order.claimed_by = None
            order.claimed_at = None
            order.save(update_fields=["order_status", "claimed_by", "claimed_at"])
            broadcast_order_status(order.id, "O", error=error_message)

        else:
            return Response(
                {"detail": "outcome must be 'complete' or 'error'."}, status=400
            )

        return Response({"ok": True})
