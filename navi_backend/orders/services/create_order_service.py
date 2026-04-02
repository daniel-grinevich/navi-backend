from collections import Counter
from contextlib import contextmanager

from django.db import transaction
from rest_framework.exceptions import ValidationError

from navi_backend.core.base_service import BaseService
from navi_backend.menu.models import CustomizationGroup
from navi_backend.orders.models import Order
from navi_backend.payments.services import StripePaymentService


class CreateOrderService(BaseService):
    def __init__(self, **kwargs):
        self.mro = [
            self.initialize_params,
            self.validate_customizations,
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
        validated_data["cart_token"] = (
            auth_parts[1] if len(auth_parts) > 1 else "FakeToken"
        )

        ctx["validated_data"] = validated_data
        return ctx

    def validate_customizations(self, ctx):
        """
        Enforce CustomizationGroup rules (is_required, allow_multiple,
        minimum_allowed, maximum_allowed) for each order item.
        """
        errors = []

        for idx, item_data in enumerate(ctx["order_items_data"]):
            menu_item = item_data.get("menu_item")
            if not menu_item or not menu_item.category:
                continue

            customizations = item_data.get("customizations", [])

            # Count how many customizations were selected per group
            group_counts = Counter()
            for c in customizations:
                customization = c.get("customization")
                if customization and customization.group_id:
                    group_counts[customization.group_id] += c.get("quantity", 1)

            # Get all customization groups for this item's category
            groups = CustomizationGroup.objects.filter(category=menu_item.category)

            for group in groups:
                count = group_counts.get(group.pk, 0)
                item_label = f"Item {idx + 1} ({menu_item.name})"

                if group.is_required and count == 0:
                    errors.append(f'{item_label}: "{group.name}" is required.')
                    continue

                if count == 0:
                    continue

                if not group.allow_multiple and count > 1:
                    errors.append(
                        f'{item_label}: "{group.name}" only allows a single selection.'
                    )

                if group.minimum_allowed is not None and count < group.minimum_allowed:
                    errors.append(
                        f'{item_label}: "{group.name}" requires at least '
                        f"{group.minimum_allowed} selection(s)."
                    )

                if group.maximum_allowed is not None and count > group.maximum_allowed:
                    errors.append(
                        f'{item_label}: "{group.name}" allows at most '
                        f"{group.maximum_allowed} selection(s)."
                    )

        if errors:
            raise ValidationError({"customizations": errors})

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
