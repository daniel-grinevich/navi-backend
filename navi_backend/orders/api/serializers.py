from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from navi_backend.core.api.serializers import ReadOnlyAuditMixin
from navi_backend.menu.models import Customization
from navi_backend.menu.models import MenuItem
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.payments.services import StripePaymentService
from navi_backend.users.api.serializers import UserSerializer


class OrderCustomizationSerializer(serializers.ModelSerializer):
    order_item = serializers.PrimaryKeyRelatedField(
        queryset=OrderItem.objects.all(), required=False
    )
    unit_price = serializers.DecimalField(
        max_digits=8, decimal_places=2
    )  # read only does fuck this... lets come up with a bypass on create
    customization = serializers.PrimaryKeyRelatedField(
        queryset=Customization.objects.all()
    )

    class Meta:
        model = OrderCustomization
        fields = [
            "order_item",
            "customization",
            "quantity",
            "unit_price",
        ]


class OrderItemSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
    customizations = OrderCustomizationSerializer(many=True, required=False)
    unit_price = serializers.DecimalField(
        read_only=True, max_digits=8, decimal_places=2
    )
    menu_item = serializers.PrimaryKeyRelatedField(queryset=MenuItem.objects.all())

    class Meta:
        model = OrderItem
        fields = [
            "menu_item",
            "order",
            "customizations",
            "unit_price",
            "quantity",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]


class OrderSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, required=False)
    user = UserSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "navi_port",
            "price",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
            "items",
            "status",
        ]

    def create(self, validated_data):
        order_item_payload = validated_data.pop("items", [])
        request_user = validated_data.get("user", self.context["request"].user)
        tracking_user = validated_data.get("created_by", request_user)
        auth_parts = self.context["request"].headers.get("Authorization", "").split()
        validated_data["cart_token"] = auth_parts[1] if len(auth_parts) > 1 else None

        try:
            with transaction.atomic():
                order = Order.objects.create(**validated_data)

                for order_item_data in order_item_payload:
                    customization_payload = order_item_data.pop("customizations", [])
                    order_item_data["order"] = order.id
                    order_item_data["unit_price"] = order_item_data["menu_item"].price
                    order_item_data["menu_item"] = order_item_data["menu_item"].id

                    order_item_serializer = OrderItemSerializer(data=order_item_data)

                    if not order_item_serializer.is_valid():
                        raise ValidationError(order_item_serializer.errors)

                    created_order_item = order_item_serializer.save(
                        created_by=tracking_user, updated_by=tracking_user
                    )

                    for customization_data in customization_payload:
                        order_customization_serializer = OrderCustomizationSerializer(
                            data={
                                "customization": customization_data["customization"].id,
                                "order_item": created_order_item.id,
                                "quantity": customization_data["quantity"],
                                "unit_price": customization_data["customization"].price,
                            }
                        )

                        if not order_customization_serializer.is_valid():
                            raise ValidationError(order_customization_serializer.errors)

                        order_customization_serializer.save(
                            created_by=tracking_user, updated_by=tracking_user
                        )

                client_secret, payment = StripePaymentService.create_payment_intent(
                    order
                )
                order.payment = payment
                order._stripe_client_secret = client_secret  # noqa: SLF001
                order.save(update_fields=["payment"])
        except Exception as e:
            raise ValidationError({"error": str(e)}) from e

        return order
