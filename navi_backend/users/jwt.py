from django.conf import settings
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """Reads the access token from the cookie instead of the Authorization header."""

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_ACCESS"])
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token


def set_token_cookies(
    response: Response,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> None:
    if access_token:
        response.set_cookie(
            key=settings.SIMPLE_JWT["AUTH_COOKIE_ACCESS"],
            value=access_token,
            path="/",
            max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            secure=settings.SIMPLE_JWT["AUTH_COOKIE_SECURE"],
            domain=settings.SIMPLE_JWT["AUTH_COOKIE_DOMAIN"],
            httponly=settings.SIMPLE_JWT["AUTH_COOKIE_HTTPONLY"],
            samesite=settings.SIMPLE_JWT["AUTH_COOKIE_SAMESITE"],
        )

    if refresh_token:
        response.set_cookie(
            key=settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"],
            value=refresh_token,
            path="/",
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            secure=settings.SIMPLE_JWT["AUTH_COOKIE_SECURE"],
            domain=settings.SIMPLE_JWT["AUTH_COOKIE_DOMAIN"],
            httponly=settings.SIMPLE_JWT["AUTH_COOKIE_HTTPONLY"],
            samesite=settings.SIMPLE_JWT["AUTH_COOKIE_SAMESITE"],
        )


def delete_token_cookies(response: Response) -> None:
    response.delete_cookie(
        key=settings.SIMPLE_JWT["AUTH_COOKIE_ACCESS"],
        path="/",
        domain=settings.SIMPLE_JWT["AUTH_COOKIE_DOMAIN"],
        samesite=settings.SIMPLE_JWT["AUTH_COOKIE_SAMESITE"],
    )
    response.delete_cookie(
        key=settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"],
        path="/",
        domain=settings.SIMPLE_JWT["AUTH_COOKIE_DOMAIN"],
        samesite=settings.SIMPLE_JWT["AUTH_COOKIE_SAMESITE"],
    )
