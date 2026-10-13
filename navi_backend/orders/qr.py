"""Signed QR tokens for order pickup.

The customer's phone renders ``make_qr_token(order)`` as a QR code. The
Raspberry Pi scans it and posts the token back; ``read_qr_token`` verifies the
signature and returns the order id. The raw order UUID is never exposed in the
QR payload, and the signature makes the token tamper-proof.

Each token also carries the order's current ``qr_nonce``. The nonce is rotated
(``rotate_qr_nonce``) whenever the order moves -- claimed, released, completed --
so a screenshot of an earlier QR stops working even while it is still inside
``QR_MAX_AGE_SECONDS``. The phone refetches the order, so it always shows a
token minted with the live nonce.
"""

from django.core import signing

from navi_backend.orders.models import Order
from navi_backend.orders.models import generate_qr_nonce

# Namespaces the signature so these tokens can't be reused as any other signed
# value in the project (and vice-versa).
QR_SALT = "orders.qr.pickup"

# How long a scanned token stays valid, in seconds. The token is re-minted on
# every order fetch, so this only bounds how long a screenshot stays usable.
QR_MAX_AGE_SECONDS = 60 * 5


class InvalidQrTokenError(Exception):
    """Raised when a scanned token is malformed, tampered with, expired, or stale."""


def rotate_qr_nonce(order) -> None:
    """Invalidate every QR token minted so far for ``order``.

    Call on each status move (claim, release, complete). Accepts an Order or
    its pk; updates the instance in place when given one.
    """
    nonce = generate_qr_nonce()
    order_id = getattr(order, "pk", order)
    Order.objects.filter(pk=order_id).update(qr_nonce=nonce)
    if isinstance(order, Order):
        order.qr_nonce = nonce


def make_qr_token(order) -> str:
    """Return an opaque, signed token encoding ``order``'s id and current nonce."""
    return signing.dumps({"o": str(order.id), "n": order.qr_nonce}, salt=QR_SALT)


def read_qr_token(token: str, max_age: int = QR_MAX_AGE_SECONDS) -> str:
    """Verify ``token`` and return the encoded order id.

    Raises :class:`InvalidQrTokenError` if the token is bad, older than
    ``max_age``, or minted before the order's nonce was last rotated.
    """
    try:
        payload = signing.loads(token, salt=QR_SALT, max_age=max_age)
    except signing.SignatureExpired as exc:
        msg = "QR token has expired."
        raise InvalidQrTokenError(msg) from exc
    except signing.BadSignature as exc:
        msg = "QR token is invalid."
        raise InvalidQrTokenError(msg) from exc

    if not isinstance(payload, dict) or not {"o", "n"} <= payload.keys():
        msg = "QR token is invalid."
        raise InvalidQrTokenError(msg)

    order_id = payload["o"]
    if not Order.objects.filter(pk=order_id, qr_nonce=payload["n"]).exists():
        msg = "QR token is no longer valid; refresh the order to get a new code."
        raise InvalidQrTokenError(msg)
    return order_id
