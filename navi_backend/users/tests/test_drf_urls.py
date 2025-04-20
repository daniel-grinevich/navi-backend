from django.urls import resolve
from django.urls import reverse

from navi_backend.users.models import User


def test_user_detail(user: User):
    assert reverse("users-detail", kwargs={"pk": user.pk}) == f"/api/users/{user.pk}/"
    assert resolve(f"/api/users/{user.pk}/").view_name == "users-detail"


def test_user_list():
    assert reverse("users-list") == "/api/users/"
    assert resolve("/api/users/").view_name == "users-list"


def test_user_me():
    assert reverse("users-me") == "/api/users/me/"
    assert resolve("/api/users/me/").view_name == "users-me"
