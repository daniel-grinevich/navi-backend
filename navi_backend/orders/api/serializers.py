import stripe
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from navi_backend.core.api.serializers import ReadOnlyAuditMixin
from navi_backend.menu.models import Customization
from navi_backend.menu.models import MenuItem
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.payments.models import Payment
from navi_backend.users.api.serializers import UserSerializer


class OrderCustomizationSerializer(serializers.ModelSerializer):
    order_item = serializers.PrimaryKeyRelatedField(read_only=True)
    unit_price = serializers.DecimalField(
        read_only=True, max_digits=8, decimal_places=2
    )
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
            "order_status",
        ]

    def create(self, validated_data):
        order_item_payload = validated_data.pop("items", [])
        user = self.context["request"].user

        try:
            with transaction.atomic():
                validated_data["cart_token"] = (
                    self.context["request"].headers["Authorization"].split()[1] or None
                )
                order = Order.objects.create(**validated_data)

                for order_item in order_item_payload:
                    customizations_data = order_item.pop("customizations", [])
                    menu_item = order_item["menu_item"]
                    created_order_item = OrderItem.objects.create(
                        unit_price=menu_item.price,
                        quantity=order_item["quantity"],
                        created_by=user,
                        updated_by=user,
                        order=order,
                        menu_item=menu_item,
                    )
                    for customization_data in customizations_data:
                        customization = customization_data["customization"]
                        OrderCustomization.objects.create(
                            unit_price=customization.price,
                            created_by=user,
                            updated_by=user,
                            order_item=created_order_item,
                            **customization_data,
                        )
                try:
                    intent = stripe.PaymentIntent.create(
                        amount=int(order.price * 1000),
                        currency="usd",
                        api_key=settings.STRIPE_API_KEY,
                        payment_method_types=["card"],
                    )
                    payment = Payment.objects.create(
                        stripe_payment_intent_id=intent["client_secret"],
                        created_by=user,
                        updated_by=user,
                    )
                    order.payment = payment
                    order.save(update_fields=["payment"])
                except stripe.error.StripeError as e:
                    raise SystemError({"payment": f"Stripe error: {e!s}"}) from e
        except Exception as e:
            raise ValidationError({"error": str(e)}) from e

        return order
