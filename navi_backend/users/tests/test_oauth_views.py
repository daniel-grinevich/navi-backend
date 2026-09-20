"""End-to-end tests for the async Google OAuth callback view.

Google is faked at the httpx2 transport layer (MockTransport swapped in via
the module's ``_client`` factory), so these exercise the real async view
code path through Django's AsyncClient.
"""

import httpx2
import pytest
from asgiref.sync import sync_to_async
from django.core import signing

from navi_backend.users.api import oauth_views
from navi_backend.users.models import User
from navi_backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db(transaction=True)

CALLBACK_PATH = "/api/oauth/google/callback/"
HTTP_FOUND = 302


class FakeGoogle:
    """Routes the view's outbound calls to canned token/userinfo responses."""

    def __init__(self):
        self.token_json = {"access_token": "google-token"}
        self.token_status = 200
        self.userinfo_json = {}

    def set_user(self, email, name="Test User", *, verified=True):
        self.userinfo_json = {
            "email": email,
            "name": name,
            "email_verified": verified,
        }

    def handler(self, request):
        url = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        if request.method == "POST" and url == oauth_views.GOOGLE_TOKEN_URL:
            return httpx2.Response(self.token_status, json=self.token_json)
        if request.method == "GET" and url == oauth_views.GOOGLE_USERINFO_URL:
            return httpx2.Response(200, json=self.userinfo_json)
        return httpx2.Response(404)


@pytest.fixture
def google(monkeypatch) -> FakeGoogle:
    fake = FakeGoogle()
    monkeypatch.setattr(
        oauth_views,
        "_client",
        lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(fake.handler)),
    )
    return fake


def _state(next_path: str = "/menu") -> str:
    return signing.dumps({"next": next_path}, salt=oauth_views.STATE_SALT)


def _redirects_to_login_error(response, error: str, settings) -> bool:
    base = settings.FRONTEND_URL.rstrip("/")
    return (
        response.status_code == HTTP_FOUND
        and response["Location"] == f"{base}/login?error={error}"
    )


async def test_denied_consent(async_client, settings):
    response = await async_client.get(CALLBACK_PATH, {"error": "access_denied"})
    assert _redirects_to_login_error(response, "oauth_denied", settings)


async def test_bad_state(async_client, settings):
    response = await async_client.get(
        CALLBACK_PATH, {"code": "abc", "state": "tampered"}
    )
    assert _redirects_to_login_error(response, "oauth_state", settings)


async def test_missing_code(async_client, settings):
    response = await async_client.get(CALLBACK_PATH, {"state": _state()})
    assert _redirects_to_login_error(response, "oauth_no_code", settings)


async def test_exchange_failure(async_client, settings, google):
    google.token_status = 500
    response = await async_client.get(CALLBACK_PATH, {"code": "abc", "state": _state()})
    assert _redirects_to_login_error(response, "oauth_exchange", settings)


async def test_unverified_email(async_client, settings, google):
    google.set_user("new@example.com", verified=False)
    response = await async_client.get(CALLBACK_PATH, {"code": "abc", "state": _state()})
    assert _redirects_to_login_error(response, "oauth_unverified", settings)


async def test_new_user_created_and_cookies_set(async_client, settings, google):
    google.set_user("New@Example.com", name="New User")

    response = await async_client.get(
        CALLBACK_PATH, {"code": "abc", "state": _state("/menu")}
    )

    assert response.status_code == HTTP_FOUND
    base = settings.FRONTEND_URL.rstrip("/")
    assert response["Location"] == f"{base}/menu"

    user = await User.objects.aget(email="new@example.com")
    assert user.name == "New User"
    assert not user.is_guest
    assert not user.has_usable_password()

    assert settings.SIMPLE_JWT["AUTH_COOKIE_ACCESS"] in response.cookies
    assert settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"] in response.cookies


async def test_guest_user_upgraded(async_client, settings, google):
    guest = await sync_to_async(UserFactory)(
        email="guest@example.com", name="", is_guest=True
    )
    google.set_user("guest@example.com", name="Guest Person")

    response = await async_client.get(CALLBACK_PATH, {"code": "abc", "state": _state()})

    assert response.status_code == HTTP_FOUND
    await guest.arefresh_from_db()
    assert not guest.is_guest
    assert guest.name == "Guest Person"


async def test_open_redirect_guard(async_client, settings, google):
    google.set_user("new2@example.com")

    response = await async_client.get(
        CALLBACK_PATH,
        {"code": "abc", "state": _state("https://evil.example.com")},
    )

    assert response.status_code == HTTP_FOUND
    base = settings.FRONTEND_URL.rstrip("/")
    assert response["Location"] == f"{base}/"
