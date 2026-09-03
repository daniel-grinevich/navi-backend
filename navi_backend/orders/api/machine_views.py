from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.awards.tasks import process_order_awards
from navi_backend.core.permissions import IsMachineAuthenticated
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.models import Order
from navi_backend.orders.tasks import create_order_invoice
from navi_backend.orders.utils import broadcast_order_status
from navi_backend.payments.services import StripePaymentService

from .serializers import MachineOrderSerializer


class MachineOrderStartView(APIView):
    permission_classes = [IsMachineAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        navi_port = request.raspberry_pi.navi_port.first()
        if not navi_port:
            return Response(
                {"detail": "Machine has no associated NaviPort."}, status=400
            )

        if order.navi_port and order.navi_port.pk != navi_port.pk:
            return Response(
                {"detail": "This order is assigned to a different location."},
                status=400,
            )

        if order.order_status != "O":
            return Response(
                {
                    "detail": "Order is not in a state that can be started.",
                    "order_status": order.order_status,
                },
                status=400,
            )

        order.navi_port = navi_port
        order.order_status = "S"
        order.save(update_fields=["navi_port", "order_status"])

        broadcast_order_status(order.id, "S")

        serializer = MachineOrderSerializer(order)
        return Response(serializer.data)


class MachineOrderCompleteView(APIView):
    permission_classes = [IsMachineAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        outcome = request.data.get("outcome")
        error_message = request.data.get("error_message", "")

        if outcome == "complete":
            StripePaymentService.capture_payment(order.payment.stripe_payment_intent_id)
            order.order_status = "D"
            order.save(update_fields=["order_status"])
            broadcast_order_status(order.id, "D")
            create_order_invoice.apply_async(args=[order.id], queue="invoice")
            process_order_awards.apply_async(args=[str(order.id)])

        elif outcome == "error":
            MachineErrorLog.objects.create(
                order=order,
                raspberry_pi=request.raspberry_pi,
                error_message=error_message,
            )
            order.order_status = "O"
            order.save(update_fields=["order_status"])
            broadcast_order_status(order.id, "O", error=error_message)

        else:
            return Response(
                {"detail": "outcome must be 'complete' or 'error'."}, status=400
            )

        return Response({"ok": True})
