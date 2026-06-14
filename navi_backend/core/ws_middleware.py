from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.exceptions import TokenError
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
def _get_user(token_str):
    try:
        UntypedToken(token_str)
        jwt_auth = JWTAuthentication()
        validated = jwt_auth.get_validated_token(token_str.encode())
        return jwt_auth.get_user(validated)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


class JWTCookieAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            cookies = _parse_cookies(scope)
            cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE_ACCESS", "access_token")
            token = cookies.get(cookie_name)
            scope["user"] = await _get_user(token) if token else AnonymousUser()
        return await self.inner(scope, receive, send)


def JWTCookieAuthMiddlewareStack(inner):
    return JWTCookieAuthMiddleware(inner)
