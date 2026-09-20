"""A thin structured-logging shim over the stdlib logger.

The goal is one consistent way to emit logs across the codebase: a stable,
low-cardinality *event name* as the message and all variable data as keyword
fields, e.g.::

    from navi_backend.core.logging import get_logger

    log = get_logger(__name__)
    log.warning("order_not_found", order_id=order_id)

That renders (via ``JSONFormatter``) as::

    {"message": "order_not_found", "order_id": 42, "request_id": "...", ...}

so Loki/LogQL can filter on ``message="order_not_found"`` and ``order_id="42"``
instead of grepping free text.

This is deliberately *not* a logging framework. It wraps ``logging.getLogger``
so the existing dictConfig, JSON formatter and request-context filter keep
working untouched; request/task context (request_id, user_id, ...) is still
injected by ``LogContextFilter`` at format time, not here.
"""

import logging

from navi_backend.core.logging.formatters import _BUILTIN_ATTRS

# Keys the stdlib reserves on a LogRecord. Passing any of these in ``extra``
# makes ``Logger.makeRecord`` raise KeyError, so we prefix collisions instead
# — logging must never crash a request.
_RESERVED_KEYS: frozenset[str] = _BUILTIN_ATTRS | {"message", "asctime"}

# Frames between the caller and stdlib's ``Logger.log``: caller -> public
# method (info/warning/...) -> _log -> logger.log. So the real caller is 3 up,
# which keeps module/lineno/funcName pointing at the call site, not this file.
_STACKLEVEL = 3


class StructuredLogger:
    """Wraps a stdlib logger to emit ``event`` + structured fields."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(
        self,
        level: int,
        event: str,
        fields: dict[str, object],
        *,
        exc_info: bool = False,
    ) -> None:
        safe = {
            (f"field_{key}" if key in _RESERVED_KEYS else key): value
            for key, value in fields.items()
        }
        self._logger.log(
            level,
            event,
            extra=safe,
            exc_info=exc_info,
            stacklevel=_STACKLEVEL,
        )

    def debug(self, event: str, **fields: object) -> None:
        self._log(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: object) -> None:
        self._log(logging.INFO, event, fields)

    def warning(self, event: str, **fields: object) -> None:
        self._log(logging.WARNING, event, fields)

    def error(self, event: str, **fields: object) -> None:
        self._log(logging.ERROR, event, fields)

    def exception(self, event: str, **fields: object) -> None:
        """Log at ERROR with the active exception's traceback attached."""
        self._log(logging.ERROR, event, fields, exc_info=True)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)
