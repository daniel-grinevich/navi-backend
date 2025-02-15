from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

# from navi_backend.fakeapi.api.views import OptionSetsViewSet
from navi_backend.fakeapi.api.views import OptionViewSet
from navi_backend.fakeapi.api.views import ProductViewSet

# from navi_backend.fakeapi.api.views import FakeApiViewSet
from navi_backend.users.api.views import UserViewSet

from navi_backend.orders.api.views import (
    OrderViewSet,
    MenuItemViewSet,
    OrderItemViewSet,
    PortViewSet,
    PaymentTypeViewSet,
)

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register(r"products", ProductViewSet, basename="products")
router.register(r"options", OptionViewSet, basename="options")
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"menuitems", MenuItemViewSet, basename="menuitems")
router.register(
    r"orders/(?P<order_id>\d+)/items", OrderItemViewSet, basename="orderitems"
)
router.register(r"ports", PortViewSet, basename="ports")
router.register(r"paymenttypes", PaymentTypeViewSet, basename="paymenttypes")
# router.register(r"optionsets", OptionSetsViewSet)

app_name = "api"
urlpatterns = router.urls
