from rest_framework import serializers

from navi_backend.core.api import BaseModelSerializer
from navi_backend.core.api.mixins import ReadOnlyAuditMixin
from navi_backend.devices.services.port_status import ensure_port_accepting_orders
from navi_backend.devices.services.port_status import ensure_port_supports_items
from navi_backend.menu.models import Customization
from navi_backend.menu.models import MenuItem
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.orders.qr import make_qr_token
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
    # Only orderable items: archived/inactive/deleted ones keep a stored price
    # but must not be purchasable.
    menu_item = serializers.PrimaryKeyRelatedField(queryset=MenuItem.objects.active())

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


class MachineOrderCustomizationSerializer(serializers.ModelSerializer):
    customization_name = serializers.CharField(
        source="customization.name", read_only=True
    )

    class Meta:
        model = OrderCustomization
        fields = ["customization_name", "quantity"]


class MachineOrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    customizations = MachineOrderCustomizationSerializer(many=True, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["menu_item_name", "quantity", "customizations"]


class MachineOrderSerializer(serializers.ModelSerializer):
    items = MachineOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "order_status", "is_test", "items"]


class RefundRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class OrderSerializer(BaseModelSerializer):
    items = OrderItemSerializer(many=True, required=False)
    user = UserSerializer(read_only=True)
    qr_token = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    tax = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    show_only_to_admin_fields = ()
    # Status moves only through services (machine scan/complete, cancel,
    # dispatch) and routing is fixed at checkout; customers can't rewrite
    # either on an existing order.
    staff_only_update_fields = ("order_status", "navi_port")

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "navi_port",
            "price",
            "subtotal",
            "tax",
            "total",
            "slug",
            "items",
            "order_status",
            "qr_token",
            "created_at",
        ]

        field_sets = {
            "partial_update": ["navi_port", "items", "order_status"],
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None:
            # Orders are always placed at a specific NaviPort: it scopes which
            # Pi may see and claim the order, and sets the tax jurisdiction.
            navi_port = attrs.get("navi_port")
            if not navi_port:
                raise serializers.ValidationError(
                    {"navi_port": "Choose a NaviPort location for this order."}
                )
            # Only new orders: an existing order keeps its place even if the
            # port is paused afterwards.
            ensure_port_accepting_orders(navi_port)
            ensure_port_supports_items(
                navi_port, [item["menu_item"] for item in attrs.get("items", [])]
            )
            return attrs
        if self._request_is_staff():
            return attrs
        blocked = [f for f in self.staff_only_update_fields if f in self.initial_data]
        if blocked:
            raise serializers.ValidationError(
                dict.fromkeys(blocked, "Only staff can change this field.")
            )
        return attrs

    def _request_is_staff(self):
        request = self.context.get("request")
        return bool(request and request.user.is_staff)

    def get_qr_token(self, obj):
        """Signed token the phone renders as a QR for the Pi to scan.

        Only meaningful while the order is still awaiting pickup.
        """
        if obj.order_status != "O":
            return None
        return make_qr_token(obj)

    def get_subtotal(self, obj):
        """Pre-tax total of the order's items."""
        return obj.price

    def get_tax(self, obj):
        """Jurisdiction tax computed by Stripe Tax at order creation."""
        if obj.payment:
            return obj.payment.tax_amount
        return None

    def get_total(self, obj):
        """Amount actually authorized on the card: subtotal + tax."""
        if obj.payment:
            return obj.payment.total_amount
        return None

    def create(self, validated_data):
        service = CreateOrderService(
            context=self.context, validated_data=validated_data
        )
        return service.result["ctx"]["order"]
