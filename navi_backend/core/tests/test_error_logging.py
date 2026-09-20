"""Tests for the global error-logging funnels: DRF handler + Celery task_failure."""

import logging
from types import SimpleNamespace

from rest_framework.exceptions import APIException
from rest_framework.exceptions import NotFound

from navi_backend.core.exceptions import custom_exception_handler
from navi_backend.core.logging.celery import log_task_failure


class _DummyView:
    pass


class ServerError(APIException):
    status_code = 502
    default_detail = "boom"


def _handle(exc):
    # Mirror DRF: the handler runs inside the active exception context.
    try:
        raise exc
    except Exception as caught:  # noqa: BLE001
        return custom_exception_handler(caught, {"view": _DummyView()})


class TestExceptionHandlerLogging:
    def test_5xx_logged_as_api_error_with_traceback(self, caplog):
        with caplog.at_level(logging.ERROR, logger="navi_backend.core.exceptions"):
            response = _handle(ServerError())
        assert response.status_code == 502
        record = caplog.records[-1]
        assert record.getMessage() == "api_error"
        assert record.status == 502
        assert record.view == "_DummyView"
        assert record.exc_info is not None

    def test_4xx_logged_as_client_error(self, caplog):
        with caplog.at_level(logging.WARNING, logger="navi_backend.core.exceptions"):
            response = _handle(NotFound())
        assert response.status_code == 404
        record = caplog.records[-1]
        assert record.getMessage() == "api_client_error"
        assert record.status == 404

    def test_unhandled_exception_returns_none(self):
        # A non-DRF exception isn't handled here; django.request logs the 500.
        assert _handle(ValueError("nope")) is None


class TestTaskFailureLogging:
    def test_logs_celery_task_failed_with_context(self, caplog):
        sender = SimpleNamespace(name="orders.tasks.create_order_invoice")
        with caplog.at_level(logging.ERROR, logger="navi_backend.core.logging.celery"):
            log_task_failure(task_id="abc123", sender=sender)
        record = caplog.records[-1]
        assert record.getMessage() == "celery_task_failed"
        assert record.task_id == "abc123"
        assert record.task_name == "orders.tasks.create_order_invoice"
