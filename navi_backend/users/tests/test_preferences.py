import pytest
from rest_framework.test import APIRequestFactory

from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.services.preferences import should_send
from navi_backend.users.api.views import UserViewSet
from navi_backend.users.models import User
from navi_backend.users.models import UserPreferences


class TestUserPreferences:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_preferences_created_with_user(self, user: User):
        # The post_save signal should create a preferences row automatically.
        assert UserPreferences.objects.filter(user=user).exists()

    def test_defaults(self, user: User):
        prefs = user.preferences
        assert prefs.theme == UserPreferences.Theme.SYSTEM
        assert prefs.language == "en"
        assert prefs.email_account is True
        assert prefs.email_marketing is False

    def test_allows_maps_channel_and_category(self, user: User):
        prefs = user.preferences
        assert prefs.allows(NotificationKind.EMAIL, NotificationCategory.ACCOUNT)
        prefs.email_marketing = False
        assert not prefs.allows(NotificationKind.EMAIL, NotificationCategory.MARKETING)

    def test_allows_unknown_combination_defaults_true(self, user: User):
        assert user.preferences.allows("push", "somethingnew")

    def test_get_preferences_endpoint(self, user: User, api_rf: APIRequestFactory):
        view = UserViewSet.as_view({"get": "preferences"})
        request = api_rf.get("/users/preferences/")
        request.user = user

        response = view(request)

        assert response.status_code == 200
        assert response.data["theme"] == UserPreferences.Theme.SYSTEM
        assert response.data["email_order_updates"] is True

    def test_patch_preferences_endpoint(self, user: User, api_rf: APIRequestFactory):
        view = UserViewSet.as_view({"patch": "preferences"})
        request = api_rf.patch(
            "/users/preferences/",
            {"theme": "dark", "email_marketing": True},
            format="json",
        )
        request.user = user

        response = view(request)

        assert response.status_code == 200
        assert response.data["theme"] == "dark"
        assert response.data["email_marketing"] is True

        user.preferences.refresh_from_db()
        assert user.preferences.theme == "dark"
        assert user.preferences.email_marketing is True

    def test_should_send_respects_opt_out(self, user: User):
        user.preferences.email_order_updates = False
        user.preferences.save()

        assert not should_send(
            user, NotificationKind.EMAIL, NotificationCategory.ORDER_UPDATES
        )
        assert should_send(user, NotificationKind.EMAIL, NotificationCategory.ACCOUNT)
