from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem

from .mixins import TrackUserMixin
from .permissions import IsOwnerOrAdmin
from .serializers import OrderCustomizationSerializer
from .serializers import OrderItemSerializer
from .serializers import OrderSerializer
from .utils import get_parent_pk


class OrderViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = OrderSerializer

    def get_permissions(self):
        """
        Assign different permissions for actions.
        """
        if self.action in [
            "list",
            "retrieve",
            "update",
            "partial_update",
            "cancel_order",
        ]:
            permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
        elif self.action == "create":
            permission_classes = [IsAuthenticated]
        elif self.action in ["destroy", "send_order_to_navi_port"]:
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all()
        token = self.request.headers["Authorization"].split()[1]
        if token and self.request.user.groups.filter(name="guest").exists():
            return Order.objects.filter(auth_token=token)

        user = self.request.user
        if user and user.is_authenticated:
            return Order.objects.filter(user=user)

        return Order.objects.none()

    @action(detail=True, methods=["put"], name="Cancel Order")
    def cancel_order(self, request, pk=None):
        """Cancels an order if it's in an ordered state ('O')."""
        slug = pk
        order = get_object_or_404(self.get_queryset(), slug=slug)

        if order.status != "O":
            return Response(
                {"detail": "Order could not be cancelled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        order.status = "C"
        order.save()
        return Response(
            {"detail": "Order cancelled successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], name="Retrieve and Mark Order as Sent")
    def send_order_to_navi_port(self, request, pk=None):
        """
        GET: Return order details and update status to 'sent' ('S').
        """
        order = get_object_or_404(self.get_queryset(), pk=pk)

        if order.status == "S":
            return Response(
                {"detail": "Order is already sent."},
                status=status.HTTP_200_OK,
            )

        if order.status != "O":  # 'O' = Open
            return Response(
                {"detail": "Order cannot be sent."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Update status to "Sent"
        order.status = "S"
        order.save()

        # Return updated order details
        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)
        order = serializer.instance

        client_secret = order.payment.stripe_payment_intent_id
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
        """
        Set the `user` field to the currently authenticated user.
        """
        serializer.validated_data["user"] = self.request.user
        super().perform_create(serializer)


class OrderItemViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = OrderItemSerializer

    def get_parent_order(self):
        order_pk = get_parent_pk(self.request.path, "orders")
        # respect order permissions
        order_viewset = OrderViewSet()
        order_viewset.request = self.request  # Inject request into OrderViewSet
        return order_viewset.get_queryset().filter(pk=order_pk).first()

    def get_queryset(self):
        """
        Restrict query to order items belonging to a specific order.
        - Admins can access all orders.
        - Regular users can only access their own order items.
        """
        order = self.get_parent_order()

        if not order:
            return (
                OrderItem.objects.none()
            )  # Return empty queryset if order doesn't exist

        if self.request.user.is_staff or order.user == self.request.user:
            return OrderItem.objects.filter(order_id=order.pk)

        return OrderItem.objects.none()  # Unauthorized users get an empty queryset

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
