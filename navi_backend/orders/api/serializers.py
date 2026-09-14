from rest_framework import serializers

from navi_backend.awards.choices import PointsReason
from navi_backend.awards.models import Reward
from navi_backend.awards.models import RewardRedemption
from navi_backend.core.api import BaseModelSerializer
from navi_backend.core.api.mixins import ReadOnlyAuditMixin
from navi_backend.menu.models import Customization
from navi_backend.menu.models import MenuItem
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.orders.qr import make_qr_token
from navi_backend.orders.services import CreateOrderService
from navi_backend.users.api.serializers import UserSerializer

EARNED_POINT_REASONS = frozenset({PointsReason.ORDER, PointsReason.PROMOTION_BONUS})


def reward_field():
    """Optional reward to redeem on a line. Only honoured when placing an order."""
    return serializers.PrimaryKeyRelatedField(
        queryset=Reward.objects.filter(is_deleted=False),
        required=False,
        allow_null=True,
        write_only=True,
    )


def reject_reward_outside_order_create(serializer, attrs):
    # Nested under OrderSerializer the root is the order; used standalone (the
    # item/customization endpoints) there is no checkout to redeem against.
    if attrs.get("reward") and serializer.root is serializer:
        raise serializers.ValidationError(
            {"reward": "Rewards can only be applied when placing an order."}
        )
    return attrs


class OrderCustomizationSerializer(BaseModelSerializer):
    order_item = serializers.PrimaryKeyRelatedField(
        queryset=OrderItem.objects.all(), required=False
    )
    unit_price = serializers.DecimalField(max_digits=8, decimal_places=2)
    customization = serializers.PrimaryKeyRelatedField(
        queryset=Customization.objects.all()
    )
    reward = reward_field()

    admin_permissions = []
    show_only_to_admin_fields = ()

    class Meta:
        model = OrderCustomization
        fields = [
            "order_item",
            "customization",
            "quantity",
            "unit_price",
            "reward",
        ]

    def validate(self, attrs):
        return reject_reward_outside_order_create(self, super().validate(attrs))


class OrderItemSerializer(ReadOnlyAuditMixin, serializers.ModelSerializer):
    customizations = OrderCustomizationSerializer(many=True, required=False)
    unit_price = serializers.DecimalField(
        read_only=True, max_digits=8, decimal_places=2
    )
    menu_item = serializers.PrimaryKeyRelatedField(queryset=MenuItem.objects.all())
    reward = reward_field()

    class Meta:
        model = OrderItem
        fields = [
            "menu_item",
            "order",
            "customizations",
            "unit_price",
            "quantity",
            "reward",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "slug",
        ]

    def validate(self, attrs):
        return reject_reward_outside_order_create(self, super().validate(attrs))


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
        fields = ["id", "order_status", "items"]


class OrderRedemptionSerializer(serializers.ModelSerializer):
    reward_name = serializers.CharField(source="reward.name", read_only=True)

    class Meta:
        model = RewardRedemption
        fields = [
            "id",
            "reward",
            "reward_name",
            "order_item",
            "order_customization",
            "points_spent",
            "discount_amount",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class OrderSerializer(BaseModelSerializer):
    items = OrderItemSerializer(many=True, required=False)
    user = UserSerializer(read_only=True)
    qr_token = serializers.SerializerMethodField()
    subtotal = serializers.ReadOnlyField()
    discount_total = serializers.ReadOnlyField()
    redemptions = OrderRedemptionSerializer(
        source="reward_redemptions", many=True, read_only=True
    )
    points_earned = serializers.SerializerMethodField()

    show_only_to_admin_fields = ()

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "navi_port",
            "price",
            "subtotal",
            "discount_total",
            "redemptions",
            "points_earned",
            "slug",
            "items",
            "order_status",
            "qr_token",
            "created_at",
        ]

        field_sets = {
            "partial_update": ["navi_port", "items", "order_status"],
        }

    def get_qr_token(self, obj):
        """Signed token the phone renders as a QR for the Pi to scan.

        Only meaningful while the order is still awaiting pickup.
        """
        if obj.order_status != "O":
            return None
        return make_qr_token(obj.id)

    def get_points_earned(self, obj) -> int:
        """Base + promotion points granted for this order (0 until completed).

        Reads the prefetched ``points_transactions`` so lists stay flat.
        """
        return sum(
            entry.points
            for entry in obj.points_transactions.all()
            if entry.reason in EARNED_POINT_REASONS
        )

    def create(self, validated_data):
        service = CreateOrderService(
            context=self.context, validated_data=validated_data
        )
        return service.result["ctx"]["order"]
