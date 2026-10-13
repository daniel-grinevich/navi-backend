from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.awards.tasks import process_order_awards
from navi_backend.core.permissions import IsMachineAuthenticated
from navi_backend.devices.models import DeviceEvent
from navi_backend.devices.services.events import record_event
from navi_backend.devices.services.port_status import PORT_PAUSED_MESSAGE
from navi_backend.orders.models import Order
from navi_backend.orders.qr import InvalidQrTokenError
from navi_backend.orders.qr import read_qr_token
from navi_backend.orders.qr import rotate_qr_nonce
from navi_backend.orders.services.fail_order_service import OrderNotClaimedError
from navi_backend.orders.services.fail_order_service import fail_order
from navi_backend.orders.services.scan_order_service import OrderNotAvailableError
from navi_backend.orders.services.scan_order_service import PaymentFailedError
from navi_backend.orders.services.scan_order_service import WrongLocationError
from navi_backend.orders.services.scan_order_service import start_order
from navi_backend.orders.tasks import create_order_invoice
from navi_backend.orders.utils import broadcast_order_status
from navi_backend.orders.utils import notify_port_queue_changed

from .serializers import MachineOrderSerializer


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


# Scan + complete call Stripe, so they must not run in one request-wide
# transaction: a late failure would roll back a charge/refund that already
# happened. The services commit each step themselves.
@method_decorator(transaction.non_atomic_requests, name="dispatch")
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

    try:
        order = start_order(order_id, request.raspberry_pi, navi_port)
    except Order.DoesNotExist as exc:
        raise Http404 from exc
    except WrongLocationError:
        return Response(
            {"detail": "This order is assigned to a different location."},
            status=400,
        )
    except OrderNotAvailableError as exc:
        return Response(
            {
                "detail": "Order is not available to start.",
                "order_status": exc.order_status,
            },
            status=409,
        )
    except PaymentFailedError as exc:
        return Response(
            {"detail": "Payment could not be completed.", "error": str(exc)},
            status=402,
        )

    record_event(
        request.raspberry_pi.pk,
        DeviceEvent.Type.ORDER_CLAIMED,
        message=f"Claimed order {order.id}",
        payload=_order_payload(order),
    )
    return Response(MachineOrderSerializer(order).data)


def _order_payload(order, **extra):
    return {"order_id": str(order.id), "is_test": order.is_test, **extra}


@method_decorator(transaction.non_atomic_requests, name="dispatch")
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

        if outcome == "error":
            # Never back to the queue: cancel + refund (see fail_order_service).
            try:
                refunded = fail_order(order, request.raspberry_pi, error_message)
            except OrderNotClaimedError:
                return Response(
                    {"detail": "Order is not claimed by this machine."}, status=409
                )
            record_event(
                request.raspberry_pi.pk,
                DeviceEvent.Type.BREW_FAILED,
                message=error_message or f"Brew failed for order {order.id}",
                payload=_order_payload(order, error_message=error_message),
            )
            return Response({"ok": True, "order_status": "C", "refunded": refunded})

        # Mirror of claim_order: one conditional UPDATE both verifies this Pi
        # still holds the claim and releases it, so a stale Pi racing a reclaim
        # can't finish an order it no longer owns.
        updated = Order.objects.filter(
            pk=order_id,
            order_status="S",
            claimed_by=request.raspberry_pi,
        ).update(order_status="D", claimed_by=None, claimed_at=None)
        if not updated:
            return Response(
                {"detail": "Order is not claimed by this machine."}, status=409
            )
        rotate_qr_nonce(order_id)

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
        notify_port_queue_changed(order.navi_port)
        return Response({"ok": True})
