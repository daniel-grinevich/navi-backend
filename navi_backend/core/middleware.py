import re
import uuid

from navi_backend.core.logging.context import clear_log_ctx
from navi_backend.core.logging.context import init_log_ctx
from navi_backend.core.logging.context import set_log_ctx_key

# Guard against header injection / log forging via a client-supplied id.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_IDEMPOTENCY_KEY_MAX_LENGTH = 255


class RequestLogContextMiddleware:
    """Bind request_id / user_id / idempotency_key into the log context.

    Sits first in MIDDLEWARE: its request phase runs before everything else so
    every log line is tagged, and its response phase runs last so the context
    is cleared only after all inner exception logging has fired.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-Request-ID", "")
        if _REQUEST_ID_RE.fullmatch(supplied):
            request_id = supplied
        else:
            request_id = uuid.uuid4().hex
        init_log_ctx()
        set_log_ctx_key("request_id", request_id)
        set_log_ctx_key("method", request.method)
        set_log_ctx_key("path", request.path)
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            set_log_ctx_key(
                "idempotency_key",
                idempotency_key[:_IDEMPOTENCY_KEY_MAX_LENGTH],
            )
        request.request_id = request_id
        try:
            response = self.get_response(request)
            # DRF's Request.user setter writes back onto the underlying
            # HttpRequest, so JWT-authenticated users are visible here even
            # though session auth saw them as anonymous.
            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                set_log_ctx_key("user_id", user.pk)
            response["X-Request-ID"] = request_id
            return response
        finally:
            clear_log_ctx()
