from django.conf import settings
from django.urls import path
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from navi_backend.awards.api.views import AchievementViewSet
from navi_backend.awards.api.views import AwardViewSet
from navi_backend.awards.api.views import LoyaltySettingsView
from navi_backend.awards.api.views import MyAwardsViewSet
from navi_backend.awards.api.views import MyLoyaltyView
from navi_backend.awards.api.views import MyPointsTransactionViewSet
from navi_backend.awards.api.views import TierViewSet
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
from navi_backend.orders.api.machine_views import MachineOrderCompleteView
from navi_backend.orders.api.machine_views import MachineOrderQueueView
from navi_backend.orders.api.machine_views import MachineOrderScanView
from navi_backend.orders.api.machine_views import MachineOrderStartView
from navi_backend.orders.api.views import OrderCustomizationViewSet
from navi_backend.orders.api.views import OrderItemViewSet
from navi_backend.orders.api.views import OrderViewSet
from navi_backend.payments.api.views import PaymentViewSet
from navi_backend.users.api.oauth_views import GoogleOAuthCallbackView
from navi_backend.users.api.oauth_views import GoogleOAuthStartView
from navi_backend.users.api.passwordless_views import MagicLinkRequestView
from navi_backend.users.api.passwordless_views import MagicLinkVerifyView
from navi_backend.users.api.passwordless_views import SMSRequestView
from navi_backend.users.api.passwordless_views import SMSVerifyView
from navi_backend.users.api.views import CreateGuestView
from navi_backend.users.api.views import CSRFAPIView
from navi_backend.users.api.views import LoginView
from navi_backend.users.api.views import LogoutAPIView
from navi_backend.users.api.views import RefreshTokenAPIView
from navi_backend.users.api.views import SignupView
from navi_backend.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

# Order routes
router.register(
    r"orders/(?P<order_pk>[0-9a-f-]+)/items/(?P<order_item_pk>[0-9a-f-]+)/customizations",
    OrderCustomizationViewSet,
    basename="order-items-customization",
)
router.register(
    r"orders/(?P<order_pk>[0-9a-f-]+)/items", OrderItemViewSet, basename="order-items"
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

# Awards / loyalty routes
router.register(r"tiers", TierViewSet, basename="tiers")
router.register(r"awards", AwardViewSet, basename="awards")
# Frontend-facing achievements contract, backed by the Award models above.
router.register(r"achievements", AchievementViewSet, basename="achievements")
router.register(r"my/awards", MyAwardsViewSet, basename="my-awards")
router.register(
    r"my/points-transactions",
    MyPointsTransactionViewSet,
    basename="my-points-transactions",
)

app_name = "api"
urlpatterns = [
    # Auth endpoints
    path("token/", LoginView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", RefreshTokenAPIView.as_view(), name="token_refresh"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("csrf-token/", CSRFAPIView.as_view(), name="csrf-token"),
    path("create-guest/", CreateGuestView.as_view(), name="create-guest"),
    # OAuth (Google) endpoints
    path("oauth/google/start/", GoogleOAuthStartView.as_view(), name="oauth-google-start"),
    path(
        "oauth/google/callback/",
        GoogleOAuthCallbackView.as_view(),
        name="oauth-google-callback",
    ),
    # Passwordless: magic link (email) + SMS OTP
    path("auth/magic/request/", MagicLinkRequestView.as_view(), name="magic-request"),
    path("auth/magic/verify/", MagicLinkVerifyView.as_view(), name="magic-verify"),
    path("auth/sms/request/", SMSRequestView.as_view(), name="sms-request"),
    path("auth/sms/verify/", SMSVerifyView.as_view(), name="sms-verify"),
    # Loyalty / awards endpoints
    path("my/loyalty/", MyLoyaltyView.as_view(), name="my-loyalty"),
    path(
        "loyalty-settings/",
        LoyaltySettingsView.as_view(),
        name="loyalty-settings",
    ),
    # Machine endpoints
    path(
        "machine/orders/queue/",
        MachineOrderQueueView.as_view(),
        name="machine-order-queue",
    ),
    path(
        "machine/orders/scan/",
        MachineOrderScanView.as_view(),
        name="machine-order-scan",
    ),
    path(
        "machine/orders/<uuid:order_id>/start/",
        MachineOrderStartView.as_view(),
        name="machine-order-start",
    ),
    path(
        "machine/orders/<uuid:order_id>/complete/",
        MachineOrderCompleteView.as_view(),
        name="machine-order-complete",
    ),
    # API documentation
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="api:api-schema"),
        name="api-docs",
    ),
]
urlpatterns += router.urls
