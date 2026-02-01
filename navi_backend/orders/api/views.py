from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from navi_backend.core.api import BaseModelViewSet
from navi_backend.core.api.mixins import UserScopedQuerySetMixin
from navi_backend.core.permissions import IsOwner
from navi_backend.core.utils.decorators import require_body_params
from navi_backend.devices.models import NaviPort
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.orders.tasks import create_order_invoice
from navi_backend.payments.services import StripePaymentService

from .mixins import TrackUserMixin
from .serializers import OrderCustomizationSerializer
from .serializers import OrderItemSerializer
from .serializers import OrderSerializer
from .utils import get_parent_pk


class OrderViewSet(UserScopedQuerySetMixin, BaseModelViewSet):
    serializer_class = OrderSerializer
    action_permissions = {
        "default": [IsOwner, IsAuthenticated],
        "create": [IsAuthenticated],
        "destroy": [IsAdminUser],
        "dispatch_order": [IsAdminUser],
    }

    @action(detail=True, methods=["put"], name="Cancel Order")
    def cancel_order(self, request, pk=None):
        slug = pk
        order = get_object_or_404(self.get_queryset(), slug=slug)

        try:
            order.is_cancelable()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)

        if order.payment and order.payment.stripe_payment_intent_id:
            StripePaymentService.cancel_payment(order.payment.stripe_payment_intent_id)

        order.status = "C"
        order.save()
        return Response(
            {"detail": "Order cancelled successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="dispatch")
    @require_body_params("naviportId")
    def dispatch_order(self, request, pk=None):
        order = get_object_or_404(self.get_queryset(), id=pk)

        try:
            order.is_dispatchable()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)

        navi_port = get_object_or_404(NaviPort, id=request.data["naviportId"])

        StripePaymentService.capture_payment(order.payment.stripe_payment_intent_id)

        order.navi_port = navi_port
        order.status = "S"
        order.save(update_fields=["navi_port", "status"])

        create_order_invoice.apply_async(args=[order.id], queue="invoice")

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        order = serializer.instance

        client_secret = order._stripe_client_secret  # noqa: SLF001
        output_data = OrderSerializer(order, context=self.get_serializer_context()).data
        headers = self.get_success_headers(output_data)
        return Response(
            {
                "order": output_data,
                "client_secret": client_secret,
            },
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def perform_create(self, serializer):
        serializer.validated_data["user"] = self.request.user
        super().perform_create(serializer)


class OrderItemViewSet(UserScopedQuerySetMixin, BaseModelViewSet):
    serializer_class = OrderItemSerializer
    user_field = "order__user"
    action_permissions = {
        "default": [IsOwner, IsAuthenticated],
        "create": [IsAuthenticated],
        "destroy": [IsAdminUser],
        "dispatch_order": [IsAdminUser],
    }

    def get_queryset(self):
        self.queryset = OrderItem.objects.filter(order_id=self.kwargs.get("order_pk"))
        return super().get_queryset()

    def perform_create(self, serializer):
        order = self.get_parent_order()

        if (not order) or (
            not self.request.user.is_staff and order.user != self.request.user
        ):
            msg = "Incorrect user for order item."
            raise Http404(msg)
        if serializer.validated_data["order"].pk != order.pk:
            msg = "Order in data does not match the order in the url."
            raise Http404(msg)
        serializer.save(
            order=order,
            unit_price=serializer.validated_data["menu_item"].price,
            created_by=self.request.user,
            updated_by=self.request.user,
        )


class OrderCustomizationViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = OrderCustomizationSerializer

    def get_parent_order(self):
        order_pk = get_parent_pk(self.request.path, "orders")
        # respect order permissions
        order_viewset = OrderViewSet()
        order_viewset.request = self.request  # Inject request into OrderViewSet
        return order_viewset.get_queryset().filter(pk=order_pk).first()

    def get_parent_order_item(self):
        order_item_pk = get_parent_pk(self.request.path, "items")
        # respect order permissions
        order_item_viewset = OrderItemViewSet()
        order_item_viewset.request = self.request  # Inject request into OrderViewSet
        return order_item_viewset.get_queryset().filter(pk=order_item_pk).first()

    def get_queryset(self):
        order = self.get_parent_order()
        order_item = self.get_parent_order_item()
        if not order_item or not order:
            return OrderCustomization.objects.none()

        return OrderCustomization.objects.filter(order_item_id=order_item.pk)

    def perform_create(self, serializer):
        order = self.get_parent_order()
        order_item = self.get_parent_order_item()

        if (not order) or (
            not self.request.user.is_staff and order.user != self.request.user
        ):
            msg = "Incorrect user for order item."
            raise Http404(msg)
        if not order_item:
            msg = "Incorrect order item for customization."
            raise Http404(msg)
        serializer.save(
            order_item=order_item,
            unit_price=serializer.validated_data["customization"].price,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
