"""Tests for the structured-logging wrapper (get_logger / StructuredLogger)."""

import json
import logging

import pytest

from navi_backend.core.logging import StructuredLogger
from navi_backend.core.logging import get_logger
from navi_backend.core.logging.formatters import JSONFormatter


def test_get_logger_returns_structured_logger():
    assert isinstance(get_logger(__name__), StructuredLogger)


class TestEventAndFields:
    def test_event_becomes_message_and_fields_become_attrs(self, caplog):
        log = get_logger("navi_backend.test.events")
        with caplog.at_level(logging.INFO, logger="navi_backend.test.events"):
            log.info("order_created", order_id=7, total="14.50")
        record = caplog.records[-1]
        assert record.getMessage() == "order_created"
        assert record.order_id == 7
        assert record.total == "14.50"

    @pytest.mark.parametrize(
        ("method", "expected_level"),
        [
            ("debug", logging.DEBUG),
            ("info", logging.INFO),
            ("warning", logging.WARNING),
            ("error", logging.ERROR),
        ],
    )
    def test_levels_map(self, caplog, method, expected_level):
        log = get_logger("navi_backend.test.levels")
        with caplog.at_level(logging.DEBUG, logger="navi_backend.test.levels"):
            getattr(log, method)("some_event")
        assert caplog.records[-1].levelno == expected_level


class TestReservedKeyGuard:
    def test_reserved_key_is_prefixed_not_dropped(self, caplog):
        # `module` is a real LogRecord attribute; passing it raw would make
        # Logger.makeRecord raise KeyError.
        log = get_logger("navi_backend.test.reserved")
        with caplog.at_level(logging.INFO, logger="navi_backend.test.reserved"):
            log.info("evt", module="mine", order_id=1)
        record = caplog.records[-1]
        assert record.field_module == "mine"
        assert record.order_id == 1
        # The real record.module still points at this test module, untouched.
        assert record.module == "test_log_wrapper"

    def test_message_key_collision_is_prefixed(self, caplog):
        log = get_logger("navi_backend.test.reserved2")
        with caplog.at_level(logging.INFO, logger="navi_backend.test.reserved2"):
            log.info("sms_console_send", message="hi there")
        record = caplog.records[-1]
        assert record.getMessage() == "sms_console_send"
        assert record.field_message == "hi there"


class TestCallerAttribution:
    def test_lineno_and_func_point_at_caller_not_wrapper(self, caplog):
        # stacklevel must skip the wrapper frames so module/lineno/funcName
        # identify the real call site.
        log = get_logger("navi_backend.test.caller")
        with caplog.at_level(logging.INFO, logger="navi_backend.test.caller"):
            log.info("evt")
        record = caplog.records[-1]
        assert record.funcName == "test_lineno_and_func_point_at_caller_not_wrapper"
        assert record.module == "test_log_wrapper"


class TestException:
    def test_exception_attaches_traceback(self, caplog):
        log = get_logger("navi_backend.test.exc")
        with caplog.at_level(logging.ERROR, logger="navi_backend.test.exc"):
            try:
                msg = "boom"
                raise ValueError(msg)
            except ValueError:
                log.exception("payment_failed", order_id=9)
        record = caplog.records[-1]
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert record.order_id == 9


class TestJSONFormatterIntegration:
    def test_rendered_json_has_event_and_fields(self, caplog):
        log = get_logger("navi_backend.test.json")
        with caplog.at_level(logging.WARNING, logger="navi_backend.test.json"):
            log.warning("order_not_found", order_id=42)
        out = JSONFormatter(fmt_keys={"level": "levelname"}).format(caplog.records[-1])
        parsed = json.loads(out)
        assert parsed["message"] == "order_not_found"
        assert parsed["order_id"] == 42
        assert parsed["level"] == "WARNING"
