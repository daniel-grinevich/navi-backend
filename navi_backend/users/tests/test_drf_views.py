import pytest
from rest_framework.test import APIRequestFactory

from navi_backend.users.api.views import UserViewSet
from navi_backend.users.models import User  # noqa: TC001


class TestUserViewSet:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_get_queryset(self, user: User, api_rf: APIRequestFactory):
        view = UserViewSet.as_view({"get": "list"})
        request = api_rf.get("/users/")
        request.user = user
        response = view(request)
        assert response.status_code == 200
        assert response.data[0]["id"] == user.id

    def test_me(self, user: User, api_rf: APIRequestFactory):
        view = UserViewSet.as_view({"get": "me"})
        request = api_rf.get("/users/")
        request.user = user

        response = view(request)

        assert user.email == response.data["email"]
