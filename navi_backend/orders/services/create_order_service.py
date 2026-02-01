from contextlib import contextmanager

from django.db import transaction
from rest_framework.exceptions import ValidationError

from navi_backend.core.base_service import BaseService
from navi_backend.orders.models import Order
from navi_backend.payments.services import StripePaymentService


class CreateOrderService(BaseService):
    def __init__(self, **kwargs):
        self.mro = [
            self.initialize_params,
            self.save_order,
            self.save_order_items,
            self.create_payment_intent,
        ]
        super().__init__(**kwargs)

    @contextmanager
    def execute(self):
        try:
            with transaction.atomic():
                yield self.mro
        except Exception as e:
            raise ValidationError({"error": str(e)}) from e

    def initialize_params(self, ctx):
        validated_data = self.kwargs.get("validated_data", {}).copy()
        request_context = self.kwargs.get("context", {})

        ctx["order_items_data"] = validated_data.pop("items", [])
        request_user = validated_data.get("user") or request_context["request"].user
        ctx["tracking_user"] = validated_data.get("created_by") or request_user

        auth_parts = request_context["request"].headers.get("Authorization", "").split()
        validated_data["cart_token"] = auth_parts[1] if len(auth_parts) > 1 else None

        ctx["validated_data"] = validated_data
        return ctx

    def save_order(self, ctx):
        ctx["order"] = Order.objects.create(**ctx["validated_data"])
        return ctx

    def save_order_items(self, ctx):
        from navi_backend.orders.api.serializers import OrderCustomizationSerializer
        from navi_backend.orders.api.serializers import OrderItemSerializer

        order = ctx["order"]
        tracking_user = ctx["tracking_user"]

        for order_item_data in ctx["order_items_data"]:
            customizations = order_item_data.pop("customizations", [])

            order_item_data["order"] = order.id
            order_item_data["unit_price"] = order_item_data["menu_item"].price
            order_item_data["menu_item"] = order_item_data["menu_item"].id

            order_item_serializer = OrderItemSerializer(data=order_item_data)
            if not order_item_serializer.is_valid():
                raise ValidationError(order_item_serializer.errors)

            order_item = order_item_serializer.save(
                created_by=tracking_user, updated_by=tracking_user
            )

            for customization_data in customizations:
                customization_serializer = OrderCustomizationSerializer(
                    data={
                        "customization": customization_data["customization"].id,
                        "order_item": order_item.id,
                        "quantity": customization_data["quantity"],
                        "unit_price": customization_data["customization"].price,
                    }
                )
                if not customization_serializer.is_valid():
                    raise ValidationError(customization_serializer.errors)

                customization_serializer.save(
                    created_by=tracking_user, updated_by=tracking_user
                )

        return ctx

    def create_payment_intent(self, ctx):
        order = ctx["order"]
        client_secret, payment = StripePaymentService.create_payment_intent(order)
        order.payment = payment
        order._stripe_client_secret = client_secret  # NOQA: SLF001
        order.save(update_fields=["payment"])
        ctx["order"] = order
        return ctx
