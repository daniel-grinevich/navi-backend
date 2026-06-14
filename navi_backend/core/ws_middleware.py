from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.tokens import UntypedToken

User = get_user_model()


def _parse_cookies(scope):
    cookies = {}
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            for pair in value.decode("utf-8").split(";"):
                key, _, val = pair.strip().partition("=")
                cookies[key.strip()] = val.strip()
    return cookies


@database_sync_to_async
def _get_user_from_access_token(token_str):
    try:
        UntypedToken(token_str)
        jwt_auth = JWTAuthentication()
        validated = jwt_auth.get_validated_token(token_str.encode())
        return jwt_auth.get_user(validated)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


@database_sync_to_async
def _get_user_from_refresh_token(token_str):
    # Access tokens expire in 5 minutes; use the refresh token (7 days) as a
    # fallback so long-lived WS connections survive without a re-login.
    try:
        token = RefreshToken(token_str)
        user_id = token.payload.get("user_id")
        if not user_id:
            return AnonymousUser()
        return User.objects.get(id=user_id)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


class JWTCookieAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            cookies = _parse_cookies(scope)
            access_name = settings.SIMPLE_JWT.get("AUTH_COOKIE_ACCESS", "access_token")
            refresh_name = settings.SIMPLE_JWT.get("AUTH_COOKIE_REFRESH", "refresh_token")
            access_token = cookies.get(access_name)
            if access_token:
                scope["user"] = await _get_user_from_access_token(access_token)
            else:
                refresh_token = cookies.get(refresh_name)
                scope["user"] = (
                    await _get_user_from_refresh_token(refresh_token)
                    if refresh_token
                    else AnonymousUser()
                )
        return await self.inner(scope, receive, send)


def JWTCookieAuthMiddlewareStack(inner):
    return JWTCookieAuthMiddleware(inner)
