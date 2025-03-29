from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

# from navi_backend.fakeapi.api.views import OptionSetsViewSet
from navi_backend.fakeapi.api.views import ProductViewSet

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
)

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register(r"products", ProductViewSet, basename="products")
router.register(
    r"orders/(?P<order_id>\d+)/items", OrderItemViewSet, basename="order_items"
)
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"menu_items", MenuItemViewSet, basename="menu_items")
router.register(r"navi_ports", NaviPortViewSet, basename="navi_ports")
router.register(r"payment_types", PaymentTypeViewSet, basename="payment_types")

router.register(r"ingredients", IngredientViewSet, basename="ingredient")
router.register(
    r"menu_item_ingredients", MenuItemIngredientViewSet, basename="menu_item_ingredient"
)

app_name = "api"
urlpatterns = router.urls
