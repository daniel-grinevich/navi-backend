from rest_framework import serializers

from navi_backend.core.api import BaseModelSerializer
from navi_backend.core.api.mixins import ReadOnlyAuditMixin
from navi_backend.menu.models import Customization
from navi_backend.menu.models import MenuItem
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.orders.services import CreateOrderService
from navi_backend.users.api.serializers import UserSerializer


class OrderCustomizationSerializer(BaseModelSerializer):
    order_item = serializers.PrimaryKeyRelatedField(
        queryset=OrderItem.objects.all(), required=False
    )
    unit_price = serializers.DecimalField(max_digits=8, decimal_places=2)
    customization = serializers.PrimaryKeyRelatedField(
        queryset=Customization.objects.all()
    )

    admin_permissions = []
    show_only_to_admin_fields = ()

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


class OrderSerializer(BaseModelSerializer):
    items = OrderItemSerializer(many=True, required=False)
    user = UserSerializer(read_only=True)

    show_only_to_admin_fields = ()

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "navi_port",
            "price",
            "slug",
            "items",
            "status",
        ]

        field_sets = {
            "partial_update": ["navi_port", "items", "status"],
        }

    def create(self, validated_data):
        service = CreateOrderService(
            context=self.context, validated_data=validated_data
        )
        return service.result["ctx"]["order"]
