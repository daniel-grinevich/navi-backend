from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter


# from navi_backend.fakeapi.api.views import FakeApiViewSet
from navi_backend.users.api.views import UserViewSet

from navi_backend.orders.api.views import (
    OrderViewSet,
    MenuItemViewSet,
    OrderItemViewSet,
    NaviPortViewSet,
    PaymentTypeViewSet,
    IngredientViewSet,
    MenuItemIngredientViewSet,
    EspressoMachineViewSet,
    RasberryPiViewSet,
    MachineTypeViewSet,
    CategoryViewSet,
    CustomizationViewSet,
    CustomizationGroupViewSet,
    OrderCustomizationViewSet,
)

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register(r"users", UserViewSet, basename="users")
router.register(
    r"orders/(?P<order_pk>\d+)/items/(?P<order_item_pk>\d+)/customizations",
    OrderCustomizationViewSet,
    basename="order-items-customization",
)
router.register(
    r"orders/(?P<order_pk>\d+)/items", OrderItemViewSet, basename="order-items"
)
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"menu_items", MenuItemViewSet, basename="menu-items")
router.register(
    r"navi_ports/(?P<navi_port_pk>\d+)/rasberry_pis",
    RasberryPiViewSet,
    basename="rasberry-pis",
)
router.register(
    r"navi_ports/(?P<navi_port_pk>\d+)/espresso_machines",
    EspressoMachineViewSet,
    basename="espresso-machines",
)
router.register(r"navi_ports", NaviPortViewSet, basename="navi-ports")
router.register(r"payment_types", PaymentTypeViewSet, basename="payment-types")

router.register(r"ingredients", IngredientViewSet, basename="ingredient")
router.register(
    r"menu_item_ingredients", MenuItemIngredientViewSet, basename="menu-item-ingredient"
)
router.register(r"machine_types", MachineTypeViewSet, basename="machine-types")
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"custimizations", CustomizationViewSet, basename="customizations")
router.register(
    r"custimization_groups", CustomizationGroupViewSet, basename="customization-groups"
)


app_name = "api"
urlpatterns = router.urls
