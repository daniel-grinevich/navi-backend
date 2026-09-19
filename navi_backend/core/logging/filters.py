import logging

from django.conf import settings

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


class StaticFieldsFilter(logging.Filter):
    """Stamp process-wide static fields (environment) onto every record.

    Lets a single Loki/Grafana instance tell staging and production apart
    (``environment="production"``) without relying on the scrape config.
    The value is read once from settings when the filter is built.
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        self.environment = getattr(settings, "ENVIRONMENT", "unknown")

    def filter(self, record: logging.LogRecord) -> bool:
        record.environment = self.environment
        return True
