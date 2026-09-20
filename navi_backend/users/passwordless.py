"""Shared helpers for passwordless sign-in (magic link + SMS OTP).

Secrets are never stored in the clear -- only their SHA-256 hash, bound to the
target (email/phone) they were issued to. Verification is single-use and
attempt-limited. On success the caller gets a User plus a freshly minted
access/refresh JWT pair (same tokens as password login) to drop into cookies.
"""

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from navi_backend.users.models import OneTimeLogin

User = get_user_model()

MAGIC_LINK_TTL = timedelta(minutes=15)
SMS_OTP_TTL = timedelta(minutes=10)
MAX_OTP_ATTEMPTS = 5


def _hash(target: str, secret: str) -> str:
    """Hash the secret bound to its target so a code can't be reused elsewhere."""
    return hashlib.sha256(f"{target}:{secret}".encode()).hexdigest()


def issue_magic_link_token(email: str) -> str:
    """Create a single-use magic-link token for ``email`` and return the raw token."""
    email = email.lower()
    token = secrets.token_urlsafe(32)
    OneTimeLogin.objects.create(
        purpose=OneTimeLogin.Purpose.MAGIC_LINK,
        target=email,
        token_hash=_hash(email, token),
        expires_at=timezone.now() + MAGIC_LINK_TTL,
    )
    return token


def issue_sms_code(phone: str) -> str:
    """Create a single-use 6-digit SMS code for ``phone`` and return the raw code."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    OneTimeLogin.objects.create(
        purpose=OneTimeLogin.Purpose.SMS_OTP,
        target=phone,
        token_hash=_hash(phone, code),
        expires_at=timezone.now() + SMS_OTP_TTL,
    )
    return code


def _consume(purpose: str, target: str, secret: str) -> bool:
    """Validate and burn the newest matching secret. True iff it was valid."""
    record = (
        OneTimeLogin.objects.filter(purpose=purpose, target=target, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if record is None or not record.is_usable:
        return False

    if record.attempts >= MAX_OTP_ATTEMPTS:
        return False

    if not secrets.compare_digest(record.token_hash, _hash(target, secret)):
        # Count the miss so a short numeric code can't be brute-forced.
        record.attempts += 1
        record.save(update_fields=["attempts"])
        return False

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    return True


def consume_magic_link_token(email: str, token: str) -> bool:
    return _consume(OneTimeLogin.Purpose.MAGIC_LINK, email.lower(), token)


def consume_sms_code(phone: str, code: str) -> bool:
    return _consume(OneTimeLogin.Purpose.SMS_OTP, phone, code)


def get_or_create_user_by_email(email: str, name: str = "") -> User:
    """Find, upgrade (guest -> full), or create a full user for ``email``."""
    email = email.lower()
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User(email=email, name=name or "", is_guest=False)
        user.set_unusable_password()
        user.save()
        return user
    if user.is_guest:
        user.is_guest = False
        user.save(update_fields=["is_guest"])
    return user


def get_or_create_user_by_phone(phone: str) -> User:
    """Find or create a full user identified by ``phone``."""
    user = User.objects.filter(phone=phone).first()
    if user is None:
        user = User(phone=phone, is_guest=False)
        user.set_unusable_password()
        user.save()
    elif user.is_guest:
        user.is_guest = False
        user.save(update_fields=["is_guest"])
    return user


def issue_jwt_pair(user) -> tuple[str, str]:
    """Return (access, refresh) JWT strings for ``user``."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)
