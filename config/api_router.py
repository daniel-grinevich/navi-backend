from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from navi_backend.fakeapi.api.views import FakeApiViewSet
from navi_backend.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("fakeapi", FakeApiViewSet)


app_name = "api"
urlpatterns = router.urls
