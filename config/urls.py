from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from knox import views as knox_views

from navi_backend.users.api.views import LoginView
from navi_backend.users.api.views import SignupView

from .api_router import router

urlpatterns = [
    path("", lambda response: JsonResponse({"status": "ok"}), name="ro"),
    path("health/", lambda response: JsonResponse({"status": "ok"}), name="health"),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("allauth.urls")),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]

# API URLS
urlpatterns += [
    # API base url
    path(r"api/", include(router.urls)),
    # Knox urls
    path(r"api/signup/", SignupView.as_view(), name="signup"),
    path(r"api/login/", LoginView.as_view(), name="login"),
    path(r"api/logout/", knox_views.LogoutView.as_view(), name="logout"),
    path(r"api/logoutall/", knox_views.LogoutAllView.as_view(), name="logout_all"),
    # API doc urls
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
]

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls)), *urlpatterns]
