"""Signed QR tokens for order pickup.

The customer's phone renders ``make_qr_token(order.id)`` as a QR code. The
Raspberry Pi scans it and posts the token back; ``read_qr_token`` verifies the
signature and returns the order id. The raw order UUID is never exposed in the
QR payload, and the signature makes the token tamper-proof.
"""

from django.core import signing

# Namespaces the signature so these tokens can't be reused as any other signed
# value in the project (and vice-versa).
QR_SALT = "orders.qr.pickup"

# How long a scanned token stays valid, in seconds. A QR shown on a phone should
# be scanned within a few minutes; this bounds replay of a leaked token.
QR_MAX_AGE_SECONDS = 60 * 30


class InvalidQrTokenError(Exception):
    """Raised when a scanned token is malformed, tampered with, or expired."""


def make_qr_token(order_id) -> str:
    """Return an opaque, signed token encoding ``order_id``."""
    return signing.dumps(str(order_id), salt=QR_SALT)


def read_qr_token(token: str, max_age: int = QR_MAX_AGE_SECONDS) -> str:
    """Verify ``token`` and return the encoded order id.

    Raises :class:`InvalidQrTokenError` if the token is bad or older than ``max_age``.
    """
    try:
        return signing.loads(token, salt=QR_SALT, max_age=max_age)
    except signing.SignatureExpired as exc:
        msg = "QR token has expired."
        raise InvalidQrTokenError(msg) from exc
    except signing.BadSignature as exc:
        msg = "QR token is invalid."
        raise InvalidQrTokenError(msg) from exc
