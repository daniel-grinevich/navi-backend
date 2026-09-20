from http import HTTPStatus

from rest_framework.views import exception_handler

from navi_backend.core.logging import get_logger

logger = get_logger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        # Not a DRF-handled exception — it propagates and Django's
        # `django.request` logger records it as a 500 (already carrying our
        # request_id/environment via the root handler). Nothing to add here.
        return None

    view = context.get("view")
    view_name = view.__class__.__name__ if view is not None else "unknown"

    if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        # exc_info attaches the traceback (the exception is still active here).
        logger.exception(
            "api_error",
            status=response.status_code,
            view=view_name,
            exc_type=type(exc).__name__,
        )
    else:
        logger.warning(
            "api_client_error",
            status=response.status_code,
            view=view_name,
            exc_type=type(exc).__name__,
        )

    response.data = {
        "error": {
            "code": response.status_code,
            "message": response.data.get("detail", response.data),
        }
    }
    return response
