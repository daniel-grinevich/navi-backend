"""Google OAuth sign-in.

Hand-rolled to match the app's custom JWT-cookie auth flow (see LoginView):
after the provider handshake we mint the SAME access/refresh cookies as a
password login via ``set_token_cookies`` and redirect the browser back to the
frontend.

Flow:
  GET /api/oauth/google/start/?next=/menu
      -> 302 to Google's consent screen (with a signed ``state`` carrying the
         post-login redirect target so the callback is stateless).
  GET /api/oauth/google/callback/?code=...&state=...
      -> exchange code for tokens, read the user's email, find/create/upgrade
         the user, set auth cookies, 302 to FRONTEND_URL + next.

The callback is a plain async Django view (not DRF): it spends most of its
time on two dependent outbound calls to Google, so awaiting them keeps a
threadpool worker free under the ASGI server. It needs nothing from DRF --
no auth, no throttling, no serializers -- and returns a bare redirect.
"""

import urllib.parse

import httpx2
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from navi_backend.users.jwt import set_token_cookies

User = get_user_model()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Namespace + lifetime for the signed ``state`` value. Signed with the Django
# SECRET_KEY so the callback can trust ``next`` without server-side storage.
STATE_SALT = "navi.oauth.google.state"
STATE_MAX_AGE_SECONDS = 600  # 10 minutes to complete the handshake.

_HTTP_TIMEOUT = 10


def _client() -> httpx2.AsyncClient:
    """Client factory; tests swap this out for one with a MockTransport."""
    return httpx2.AsyncClient(timeout=_HTTP_TIMEOUT)


def _frontend_redirect(next_path: str) -> HttpResponseRedirect:
    """Build a redirect to the frontend, guarding against open redirects.

    Only relative paths (``/menu``) are honored; anything else falls back to
    the site root so a crafted ``next`` can't bounce users to another origin.
    """
    if not isinstance(next_path, str) or not next_path.startswith("/"):
        next_path = "/"
    base = settings.FRONTEND_URL.rstrip("/")
    return HttpResponseRedirect(f"{base}{next_path}")


async def _post_form(client: httpx2.AsyncClient, url: str, data: dict) -> dict:
    resp = await client.post(url, data=data, headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


async def _get_json(client: httpx2.AsyncClient, url: str, access_token: str) -> dict:
    resp = await client.get(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    resp.raise_for_status()
    return resp.json()


class GoogleOAuthStartView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        next_path = request.GET.get("next", "/menu")
        if not next_path.startswith("/"):
            next_path = "/menu"

        state = signing.dumps({"next": next_path}, salt=STATE_SALT)

        params = {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return HttpResponseRedirect(
            f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        )


# ATOMIC_REQUESTS only supports sync views; opting out is safe here because
# the sole multi-write path (guest upgrade) is a single save() call.
@method_decorator(transaction.non_atomic_requests, name="dispatch")
class GoogleOAuthCallbackView(View):
    async def get(self, request):
        # The user denied consent or Google returned an error.
        if request.GET.get("error"):
            return _frontend_redirect("/login?error=oauth_denied")

        code = request.GET.get("code")
        state = request.GET.get("state", "")

        try:
            payload = signing.loads(
                state, salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS
            )
            next_path = payload.get("next", "/menu")
        except signing.BadSignature:
            return _frontend_redirect("/login?error=oauth_state")

        if not code:
            return _frontend_redirect("/login?error=oauth_no_code")

        try:
            email, name, email_verified = await self._fetch_identity(code)
        except (httpx2.HTTPError, ValueError, KeyError):
            return _frontend_redirect("/login?error=oauth_exchange")

        if not email or not email_verified:
            return _frontend_redirect("/login?error=oauth_unverified")

        user = await self._get_or_create_user(email.lower(), name)

        response = _frontend_redirect(next_path)
        access, refresh = await self._issue_tokens(user)
        set_token_cookies(response, access, refresh)
        return response

    async def _fetch_identity(self, code: str) -> tuple[str, str, bool]:
        """Exchange the auth code and return (email, name, email_verified).

        The two calls are dependent (userinfo needs the access token), so
        they stay sequential.
        """
        async with _client() as client:
            tokens = await _post_form(
                client,
                GOOGLE_TOKEN_URL,
                {
                    "code": code,
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            userinfo = await _get_json(
                client, GOOGLE_USERINFO_URL, tokens["access_token"]
            )
        return (
            userinfo.get("email", ""),
            userinfo.get("name", ""),
            bool(userinfo.get("email_verified", False)),
        )

    async def _get_or_create_user(self, email: str, name: str):
        """Find, upgrade (guest -> full), or create the user for this email.

        Google has verified the email, so matching an existing account and
        signing into it is safe (account linking).
        """
        user = await User.objects.filter(email=email).afirst()

        if user is None:
            # No usable password: this account signs in via Google. The user
            # can still set a password later through the normal flow.
            user = User(email=email, name=name or "", is_guest=False)
            user.set_unusable_password()
            await user.asave()
            return user

        changed = False
        if user.is_guest:
            user.is_guest = False
            changed = True
        if not user.name and name:
            user.name = name
            changed = True
        if changed:
            await user.asave()
        return user

    async def _issue_tokens(self, user) -> tuple[str, str]:
        # RefreshToken.for_user writes an OutstandingToken row (the blacklist
        # app is installed), so it has to run off the event loop.
        refresh = await sync_to_async(RefreshToken.for_user)(user)
        return str(refresh.access_token), str(refresh)
