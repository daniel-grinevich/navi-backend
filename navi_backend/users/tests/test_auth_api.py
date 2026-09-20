"""Tests for the cookie-based JWT auth flow and guest-account safety.

Covers login/refresh/logout cookie handling, refresh rotation + blacklist,
CSRF enforcement on cookie auth, and the guest-creation takeover protections
described in navi_backend/users/api/views.py.
"""

import pytest
from django.conf import settings as dj_settings
from django.urls import reverse
from rest_framework.test import APIClient

from navi_backend.users.models import User
from navi_backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = reverse("api:token_obtain_pair")
REFRESH_URL = reverse("api:token_refresh")
LOGOUT_URL = reverse("api:logout")
GUEST_URL = reverse("api:create-guest")

ACCESS_COOKIE = dj_settings.SIMPLE_JWT["AUTH_COOKIE_ACCESS"]
REFRESH_COOKIE = dj_settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"]

PASSWORD = "s3cure-Pa55word!"


@pytest.fixture
def account(db):
    user = UserFactory()
    user.set_password(PASSWORD)
    user.save()
    return user


@pytest.fixture
def client():
    return APIClient()


def login(client, account):
    return client.post(
        LOGIN_URL, {"email": account.email, "password": PASSWORD}, format="json"
    )


class TestLogin:
    def test_sets_httponly_cookies_and_keeps_tokens_out_of_body(self, client, account):
        response = login(client, account)

        assert response.status_code == 200
        assert response.data == {}
        assert response.cookies[ACCESS_COOKIE].value
        assert response.cookies[REFRESH_COOKIE].value
        assert response.cookies[ACCESS_COOKIE]["httponly"]
        assert response.cookies[REFRESH_COOKIE]["httponly"]

    def test_wrong_password_rejected_without_cookies(self, client, account):
        response = client.post(
            LOGIN_URL, {"email": account.email, "password": "nope"}, format="json"
        )

        assert response.status_code == 401
        assert ACCESS_COOKIE not in response.cookies
        assert REFRESH_COOKIE not in response.cookies

    def test_access_cookie_authenticates_requests(self, client, account):
        login(client, account)

        response = client.get(reverse("api:users-me"))

        assert response.status_code == 200
        assert response.data["email"] == account.email


class TestCsrfOnCookieAuth:
    def test_unsafe_request_without_csrf_token_rejected(self, account):
        client = APIClient(enforce_csrf_checks=True)
        login(client, account)

        response = client.patch(
            "/api/users/preferences/", {"theme": "dark"}, format="json"
        )

        assert response.status_code == 403


class TestRefresh:
    def test_rotates_tokens_and_blacklists_old_refresh(self, client, account):
        old_refresh = login(client, account).cookies[REFRESH_COOKIE].value

        response = client.post(REFRESH_URL)

        assert response.status_code == 200
        new_refresh = response.cookies[REFRESH_COOKIE].value
        assert response.cookies[ACCESS_COOKIE].value
        assert new_refresh != old_refresh

        # The rotated-out refresh token must be dead (blacklisted).
        client.cookies[REFRESH_COOKIE] = old_refresh
        assert client.post(REFRESH_URL).status_code == 401

    def test_missing_refresh_cookie_rejected(self, client):
        assert client.post(REFRESH_URL).status_code == 403

    def test_garbage_refresh_cookie_rejected(self, client):
        client.cookies[REFRESH_COOKIE] = "not-a-token"
        assert client.post(REFRESH_URL).status_code == 401


class TestLogout:
    def test_clears_cookies_and_blacklists_refresh(self, client, account):
        refresh = login(client, account).cookies[REFRESH_COOKIE].value

        response = client.post(LOGOUT_URL)

        assert response.status_code == 200
        assert response.cookies[ACCESS_COOKIE].value == ""
        assert response.cookies[REFRESH_COOKIE].value == ""

        # The blacklisted refresh token can't mint new sessions.
        client.cookies[REFRESH_COOKIE] = refresh
        assert client.post(REFRESH_URL).status_code == 401

    def test_logout_works_without_any_session(self, client):
        assert client.post(LOGOUT_URL).status_code == 200


class TestCreateGuest:
    def test_new_email_creates_guest_with_session(self, client):
        response = client.post(
            GUEST_URL, {"guestUser": "guest@example.com"}, format="json"
        )

        assert response.status_code == 201
        assert response.cookies[ACCESS_COOKIE].value
        assert User.objects.get(email="guest@example.com").is_guest

    def test_registered_email_gets_no_session_and_keeps_password(self, client, account):
        password_before = account.password

        response = client.post(GUEST_URL, {"guestUser": account.email}, format="json")

        assert response.status_code == 200
        assert response.data == {"redirect": "login"}
        assert ACCESS_COOKIE not in response.cookies
        assert REFRESH_COOKIE not in response.cookies
        account.refresh_from_db()
        assert account.password == password_before

    def test_existing_guest_email_gets_no_new_session(self, client):
        UserFactory(is_guest=True, email="guest@example.com")

        response = client.post(
            GUEST_URL, {"guestUser": "guest@example.com"}, format="json"
        )

        assert response.status_code == 409
        assert ACCESS_COOKIE not in response.cookies
        assert REFRESH_COOKIE not in response.cookies

    def test_missing_email_rejected(self, client):
        assert client.post(GUEST_URL, {}, format="json").status_code == 400
