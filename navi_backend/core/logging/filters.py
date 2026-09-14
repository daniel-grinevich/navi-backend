import logging

from navi_backend.core.logging.context import get_log_ctx


class LogContextFilter(logging.Filter):
    """Copy the current request/task context onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_log_ctx().items():
            setattr(record, key, value)
        # The plain dev format references %(request_id)s; guarantee it exists
        # for records emitted outside a request (startup, migrations, shell).
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True
