from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from navi_backend.orders.models import Category
from navi_backend.orders.models import Customization
from navi_backend.orders.models import CustomizationGroup
from navi_backend.orders.models import EspressoMachine
from navi_backend.orders.models import Ingredient
from navi_backend.orders.models import MachineType
from navi_backend.orders.models import MenuItem
from navi_backend.orders.models import MenuItemIngredient
from navi_backend.orders.models import NaviPort
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.orders.models import RasberryPi

from .mixins import TrackUserMixin
from .permissions import IsOwnerOrAdmin
from .permissions import ReadOnly
from .serializers import CategorySerializer
from .serializers import CustomizationGroupSerializer
from .serializers import CustomizationSerializer
from .serializers import EspressoMachineSerializer
from .serializers import IngredientSerializer
from .serializers import MachineTypeSerializer
from .serializers import MenuItemCustomizationSerialier
from .serializers import MenuItemIngredientSerializer
from .serializers import MenuItemSerializer
from .serializers import NaviPortSerializer
from .serializers import OrderCustomizationSerializer
from .serializers import OrderItemSerializer
from .serializers import OrderSerializer
from .serializers import RasberryPiSerializer
from .utils import getParentPK


class MenuItemViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAdminUser | ReadOnly]

    @action(
        detail=False,
        methods=["get"],
        url_path=r"(?P<slug>[^/.]+)/category-customizations",
    )
    def category_customizations(self, request, slug=None):
        """
        GET /menu_items/<slug>/category-customizations/
        """
        menu_item = get_object_or_404(MenuItem, slug=slug)
        if not menu_item.category:
            return Response(
                {"detail": "No category for that menu-item."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = MenuItemCustomizationSerialier(
            menu_item, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def add_ingredient(self, request, pk=None):
        """
        Adds an ingredient to a specific MenuItem.
        """
        menu_item = self.get_object()

        ingredient_id = request.data.get("ingredient_id")
        quantity = request.data.get("quantity")
        unit = request.data.get("unit")

        if not (ingredient_id and quantity and unit):
            return Response(
                {"error": "ingredient_id, quantity, and unit are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ingredient = Ingredient.objects.filter(id=ingredient_id).first()

        if not ingredient:
            return Response(
                {"error": "Invalid ingredient ID"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create or update the ingredient in the recipe
        menu_item_ingredient, created = MenuItemIngredient.objects.update_or_create(
            menu_item=menu_item,
            ingredient=ingredient,
            defaults={"quantity": quantity, "unit": unit},
        )

        return Response(
            MenuItemIngredientSerializer(menu_item_ingredient).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def ingredients(self, request, pk=None):
        """
        Retrieve all ingredients for a specific MenuItem.
        """
        menu_item = self.get_object()
        ingredients = menu_item.menu_item_ingredients.select_related("ingredient")
        return Response(MenuItemIngredientSerializer(ingredients, many=True).data)


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
        order_pk = getParentPK(self.request.path, "orders")
        # respect order permissions
        order_viewset = OrderViewSet()
        order_viewset.request = self.request  # Inject request into OrderViewSet
        order = order_viewset.get_queryset().filter(pk=order_pk).first()
        return order

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
            raise Http404("Incorrect user for order item.")
        if serializer.validated_data["order"].pk != order.pk:
            raise Http404("Order in data does not match the order in the url.")
        serializer.save(
            order=order,
            unit_price=serializer.validated_data["menu_item"].price,
            created_by=self.request.user,
            updated_by=self.request.user,
        )


class NaviPortViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = NaviPort.objects.all()
    serializer_class = NaviPortSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class MenuItemIngredientViewSet(viewsets.ModelViewSet):
    queryset = MenuItemIngredient.objects.select_related("menu_item", "ingredient")
    serializer_class = MenuItemIngredientSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class IngredientViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class RasberryPiViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = RasberryPiSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = getParentPK(self.request.path, "navi_ports")
        navi_port = NaviPort.objects.filter(pk=navi_port_pk).first()
        if not navi_port:
            return RasberryPi.objects.none()

        return RasberryPi.objects.filter(navi_port__pk=navi_port_pk)


class EspressoMachineViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = EspressoMachineSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        navi_port_pk = getParentPK(self.request.path, "navi_ports")
        navi_port = NaviPort.objects.filter(pk=navi_port_pk).first()
        if not navi_port:
            return EspressoMachine.objects.none()

        return EspressoMachine.objects.filter(navi_port__pk=navi_port_pk)


class MachineTypeViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = MachineTypeSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        espresso_machine_pk = getParentPK(self.request.path, "espresso_machines")
        espresso_machine = EspressoMachine.objects.filter(
            pk=espresso_machine_pk
        ).first()
        if not espresso_machine:
            return MachineType.objects.none()

        return MachineType.objects.filter(espresso_machine__pk=espresso_machine_pk)


class CustomizationViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = Customization.objects.all()
    serializer_class = CustomizationSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class CustomizationGroupViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = CustomizationGroup.objects.all()
    serializer_class = CustomizationGroupSerializer
    permission_classes = [IsAdminUser | ReadOnly]


class CategoryViewSet(TrackUserMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUser | ReadOnly]


class OrderCustomizationViewSet(TrackUserMixin, viewsets.ModelViewSet):
    serializer_class = OrderCustomizationSerializer

    def get_parent_order(self):
        order_pk = getParentPK(self.request.path, "orders")
        # respect order permissions
        order_viewset = OrderViewSet()
        order_viewset.request = self.request  # Inject request into OrderViewSet
        order = order_viewset.get_queryset().filter(pk=order_pk).first()
        return order

    def get_parent_order_item(self):
        order_item_pk = getParentPK(self.request.path, "items")
        # respect order permissions
        order_item_viewset = OrderItemViewSet()
        order_item_viewset.request = self.request  # Inject request into OrderViewSet
        order_item = order_item_viewset.get_queryset().filter(pk=order_item_pk).first()
        return order_item

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
            raise Http404("Incorrect user for order item.")
        if not order_item:
            raise Http404("Incorrect order item for customization.")
        serializer.save(
            order_item=order_item,
            unit_price=serializer.validated_data["customization"].price,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
