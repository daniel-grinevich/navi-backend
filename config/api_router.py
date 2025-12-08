from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from navi_backend.devices.api.views import EspressoMachineViewSet
from navi_backend.devices.api.views import MachineTypeViewSet
from navi_backend.devices.api.views import NaviPortViewSet
from navi_backend.devices.api.views import RaspberryPiViewSet
from navi_backend.menu.api.views import CategoryViewSet
from navi_backend.menu.api.views import CustomizationGroupViewSet
from navi_backend.menu.api.views import CustomizationViewSet
from navi_backend.menu.api.views import MenuItemViewSet
from navi_backend.notifications.api.views import EmailLogViewSet
from navi_backend.notifications.api.views import EmailTemplateViewSet
from navi_backend.notifications.api.views import TextLogViewSet
from navi_backend.orders.api.views import OrderCustomizationViewSet
from navi_backend.orders.api.views import OrderItemViewSet
from navi_backend.orders.api.views import OrderViewSet
from navi_backend.payments.api.views import PaymentViewSet
from navi_backend.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

# Order routes
router.register(
    r"orders/(?P<order_pk>\d+)/items/(?P<order_item_pk>\d+)/customizations",
    OrderCustomizationViewSet,
    basename="order-items-customization",
)
router.register(
    r"orders/(?P<order_pk>\d+)/items", OrderItemViewSet, basename="order-items"
)
router.register(r"orders", OrderViewSet, basename="orders")

# Menu routes
router.register(r"menu-items", MenuItemViewSet, basename="menu-items")
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"customizations", CustomizationViewSet, basename="customizations")
router.register(
    r"customization-groups", CustomizationGroupViewSet, basename="customization-groups"
)

# Device routes
router.register(
    r"navi_ports/(?P<navi_port_pk>\d+)/raspberry_pis",
    RaspberryPiViewSet,
    basename="raspberry-pis",
)
router.register(
    r"navi_ports/(?P<navi_port_pk>\d+)/espresso_machines",
    EspressoMachineViewSet,
    basename="espresso-machines",
)
router.register(r"navi_ports", NaviPortViewSet, basename="navi-ports")
router.register(r"machine_types", MachineTypeViewSet, basename="machine-types")

# Payment routes
router.register(r"payments", PaymentViewSet, basename="payments")

# Notification routes
router.register(r"email_logs", EmailLogViewSet, basename="email-logs")
router.register(r"text_logs", TextLogViewSet, basename="text-logs")
router.register(r"email_templates", EmailTemplateViewSet, basename="email-templates")

# User routes
router.register(r"users", UserViewSet, basename="users")


app_name = "api"
urlpatterns = router.urls
