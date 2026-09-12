"""Passwordless sign-in endpoints: magic link (email) and SMS OTP.

Magic link:
  POST /api/auth/magic/request/  {email}      -> emails a sign-in link
  GET  /api/auth/magic/verify/?email=&token=  -> sets cookies, 302 to frontend

SMS OTP:
  POST /api/auth/sms/request/  {phone}         -> texts a 6-digit code
  POST /api/auth/sms/verify/   {phone, code}   -> sets cookies, 200

Both mint the SAME JWT cookies as password login via set_token_cookies.
"""

import urllib.parse

from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.services import NotificationFactory
from navi_backend.users import passwordless
from navi_backend.users.jwt import set_token_cookies


def _frontend_redirect(next_path: str) -> HttpResponseRedirect:
    if not isinstance(next_path, str) or not next_path.startswith("/"):
        next_path = "/"
    base = settings.FRONTEND_URL.rstrip("/")
    return HttpResponseRedirect(f"{base}{next_path}")


class MagicLinkRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        # Always return 200 with the same body so this endpoint can't be used to
        # probe which emails have accounts.
        if email:
            token = passwordless.issue_magic_link_token(email)
            self._send(email, token)
        return Response(
            {"detail": "If that email is valid, a sign-in link is on its way."},
            status=status.HTTP_200_OK,
        )

    def _send(self, email: str, token: str) -> None:
        query = urllib.parse.urlencode({"email": email, "token": token})
        # Link points at the BACKEND verify endpoint so it can set the auth
        # cookies, then it redirects the browser to the frontend.
        backend = settings.BACKEND_URL.rstrip("/")
        link = f"{backend}/api/auth/magic/verify/?{query}"
        NotificationFactory.create(
            NotificationKind.EMAIL,
            recipient=email,
            subject="Your Navi sign-in link",
            template="emails/magic_link.html",
            context={"link": link, "minutes": 15},
            reason="magic_link",
        ).send()


class MagicLinkVerifyView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        email = (request.GET.get("email") or "").strip().lower()
        token = request.GET.get("token") or ""

        if not email or not token or not passwordless.consume_magic_link_token(
            email, token
        ):
            return _frontend_redirect("/login?error=magic_invalid")

        user = passwordless.get_or_create_user_by_email(email)
        response = _frontend_redirect("/menu")
        access, refresh = passwordless.issue_jwt_pair(user)
        set_token_cookies(response, access, refresh)
        return response


class SMSRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        phone = _normalize_phone(request.data.get("phone") or "")
        if phone:
            code = passwordless.issue_sms_code(phone)
            NotificationFactory.create(
                NotificationKind.SMS,
                recipient=phone,
                message=f"Your Navi code is {code}. It expires in 10 minutes.",
                reason="sms_otp",
            ).send()
        return Response(
            {"detail": "If that number is valid, a code is on its way."},
            status=status.HTTP_200_OK,
        )


class SMSVerifyView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        phone = _normalize_phone(request.data.get("phone") or "")
        code = (request.data.get("code") or "").strip()

        if not phone or not code or not passwordless.consume_sms_code(phone, code):
            return Response(
                {"detail": "That code is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = passwordless.get_or_create_user_by_phone(phone)
        response = Response(status=status.HTTP_200_OK)
        access, refresh = passwordless.issue_jwt_pair(user)
        set_token_cookies(response, access, refresh)
        return response


def _normalize_phone(raw: str) -> str:
    """Keep a leading + and digits only; drop spaces, dashes, parens."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    plus = raw.startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    return ("+" + digits) if plus else digits
