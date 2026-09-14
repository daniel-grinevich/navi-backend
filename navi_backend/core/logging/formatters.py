import datetime as dt
import json
import logging

# Attributes present on every bare LogRecord; anything else on the record is
# either an `extra` kwarg or context injected by LogContextFilter.
_BUILTIN_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    },
)


class JSONFormatter(logging.Formatter):
    """Render each record as one JSON object per line (JSON Lines)."""

    def __init__(self, *, fmt_keys: dict[str, str] | None = None) -> None:
        super().__init__()
        self.fmt_keys = fmt_keys or {}

    def format(self, record: logging.LogRecord) -> str:
        message: dict[str, object] = {
            "timestamp": dt.datetime.fromtimestamp(
                record.created,
                tz=dt.UTC,
            ).isoformat(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            message["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            message["stack_info"] = self.formatStack(record.stack_info)
        for out_key, attr in self.fmt_keys.items():
            message.setdefault(out_key, getattr(record, attr, None))
        for key, value in record.__dict__.items():
            if key not in _BUILTIN_ATTRS and key not in message:
                message[key] = value
        # default=str: an unserializable `extra` must never crash logging
        return json.dumps(message, default=str)
