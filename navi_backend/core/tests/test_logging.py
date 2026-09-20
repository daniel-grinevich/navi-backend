"""Tests for structured logging: formatter, filter, middleware, celery signals."""

import datetime as dt
import json
import logging
import sys
import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from navi_backend.core.authentication import JWTCookieAuthentication
from navi_backend.core.logging.celery import bind_task_context
from navi_backend.core.logging.celery import clear_task_context
from navi_backend.core.logging.celery import propagate_request_id
from navi_backend.core.logging.context import clear_log_ctx
from navi_backend.core.logging.context import get_log_ctx
from navi_backend.core.logging.context import init_log_ctx
from navi_backend.core.logging.context import set_log_ctx_key
from navi_backend.core.logging.filters import LogContextFilter
from navi_backend.core.logging.formatters import JSONFormatter
from navi_backend.core.middleware import RequestLogContextMiddleware


@pytest.fixture(autouse=True)
def _clean_log_ctx():
    clear_log_ctx()
    yield
    clear_log_ctx()


def make_record(msg="hello", **extra):
    record = logging.LogRecord(
        name="navi_backend.orders",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


FMT_KEYS = {"level": "levelname", "logger": "name"}


class TestJSONFormatter:
    def test_output_is_valid_json_with_core_fields(self):
        out = JSONFormatter(fmt_keys=FMT_KEYS).format(make_record())
        parsed = json.loads(out)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "navi_backend.orders"
        assert "timestamp" in parsed

    def test_timestamp_is_iso8601_utc(self):
        out = JSONFormatter().format(make_record())
        timestamp = dt.datetime.fromisoformat(json.loads(out)["timestamp"])
        assert timestamp.utcoffset() == dt.timedelta(0)

    def test_extra_kwargs_appear(self):
        out = JSONFormatter().format(make_record(order_id=7))
        assert json.loads(out)["order_id"] == 7

    def test_extra_cannot_clobber_message(self):
        record = make_record()
        record.__dict__["timestamp"] = "spoofed"
        out = JSONFormatter().format(record)
        assert json.loads(out)["timestamp"] != "spoofed"

    def test_exc_info_renders_traceback(self):
        try:
            msg = "boom"
            raise ValueError(msg)
        except ValueError:
            record = make_record()
            record.exc_info = sys.exc_info()
        out = JSONFormatter().format(record)
        assert "Traceback" in json.loads(out)["exc_info"]

    def test_unserializable_extra_does_not_raise(self):
        out = JSONFormatter().format(make_record(ref=uuid.uuid4()))
        json.loads(out)


class TestLogContextFilter:
    def test_context_keys_copied_onto_record(self):
        init_log_ctx()
        set_log_ctx_key("request_id", "abc123")
        set_log_ctx_key("user_id", 9)
        record = make_record()
        assert LogContextFilter().filter(record) is True
        assert record.request_id == "abc123"
        assert record.user_id == 9

    def test_no_context_defaults_request_id(self):
        record = make_record()
        LogContextFilter().filter(record)
        assert record.request_id == "-"


class TestRequestLogContextMiddleware:
    @pytest.fixture
    def rf(self):
        return RequestFactory()

    def make_middleware(self, captured):
        def get_response(request):
            captured.update(get_log_ctx())
            return HttpResponse()

        return RequestLogContextMiddleware(get_response)

    def test_generates_request_id_when_absent(self, rf):
        captured: dict[str, object] = {}
        response = self.make_middleware(captured)(rf.get("/api/orders/"))
        assert len(captured["request_id"]) == 32
        assert response["X-Request-ID"] == captured["request_id"]

    def test_accepts_valid_supplied_request_id(self, rf):
        captured: dict[str, object] = {}
        request = rf.get("/", headers={"x-request-id": "abc-123.DEF_456"})
        response = self.make_middleware(captured)(request)
        assert captured["request_id"] == "abc-123.DEF_456"
        assert response["X-Request-ID"] == "abc-123.DEF_456"

    @pytest.mark.parametrize(
        "bad_id",
        ["x" * 65, "has space", "uniçode", "semi;colon"],
    )
    def test_rejects_invalid_supplied_request_id(self, rf, bad_id):
        captured: dict[str, object] = {}
        request = rf.get("/", headers={"x-request-id": bad_id})
        response = self.make_middleware(captured)(request)
        assert captured["request_id"] != bad_id
        assert response["X-Request-ID"] != bad_id

    def test_binds_method_path_and_idempotency_key(self, rf):
        captured: dict[str, object] = {}
        request = rf.post("/api/orders/", headers={"idempotency-key": "k1"})
        self.make_middleware(captured)(request)
        assert captured["method"] == "POST"
        assert captured["path"] == "/api/orders/"
        assert captured["idempotency_key"] == "k1"

    def test_sets_request_attribute(self, rf):
        request = rf.get("/")
        RequestLogContextMiddleware(lambda r: HttpResponse())(request)
        assert len(request.request_id) == 32

    def test_context_cleared_after_response(self, rf):
        self.make_middleware({})(rf.get("/"))
        assert get_log_ctx() == {}

    def test_context_cleared_when_view_raises(self, rf):
        def raising_view(request):
            msg = "kaput"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            RequestLogContextMiddleware(raising_view)(rf.get("/"))
        assert get_log_ctx() == {}

    def test_binds_user_id_for_authenticated_user(self, rf):
        user = SimpleNamespace(is_authenticated=True, pk=42)
        seen = {}

        def get_response(request):
            request.user = user
            return HttpResponse()

        original_clear = clear_log_ctx

        def spy_clear():
            seen.update(get_log_ctx())
            original_clear()

        with mock.patch(
            "navi_backend.core.middleware.clear_log_ctx",
            side_effect=spy_clear,
        ):
            RequestLogContextMiddleware(get_response)(rf.get("/"))
        assert seen["user_id"] == 42

    def test_response_header_via_client(self, client):
        # Any path goes through the middleware chain — even a 404.
        response = client.get("/definitely-not-a-route/")
        assert "X-Request-ID" in response


class TestCelerySignals:
    def test_publish_injects_request_id_from_context(self):
        init_log_ctx()
        set_log_ctx_key("request_id", "req-1")
        headers: dict[str, str] = {}
        propagate_request_id(headers=headers)
        assert headers["request_id"] == "req-1"

    def test_publish_without_context_leaves_headers_alone(self):
        headers: dict[str, str] = {}
        propagate_request_id(headers=headers)
        assert headers == {}

    def test_task_prerun_binds_context(self):
        task = SimpleNamespace(
            name="orders.tasks.confirm",
            request=SimpleNamespace(request_id="req-2"),
        )
        bind_task_context(task_id="tid-1", task=task)
        ctx = get_log_ctx()
        assert ctx["task_id"] == "tid-1"
        assert ctx["task_name"] == "orders.tasks.confirm"
        assert ctx["request_id"] == "req-2"

    def test_task_postrun_clears_context(self):
        init_log_ctx()
        set_log_ctx_key("task_id", "tid-1")
        clear_task_context()
        assert get_log_ctx() == {}


class TestAuthenticationBindsUserId:
    def test_authenticate_sets_user_id(self, rf, settings):
        settings.SIMPLE_JWT = {
            **settings.SIMPLE_JWT,
            "AUTH_COOKIE_USE_CSRF": False,
        }
        auth = JWTCookieAuthentication()
        request = rf.get("/")
        request.COOKIES[settings.SIMPLE_JWT["AUTH_COOKIE_ACCESS"]] = "tok"
        user = SimpleNamespace(pk=7, is_authenticated=True)
        with (
            mock.patch.object(auth, "get_validated_token", return_value="vt"),
            mock.patch.object(auth, "get_user", return_value=user),
        ):
            result = auth.authenticate(request)
        assert result == (user, "vt")
        assert get_log_ctx()["user_id"] == 7

    @pytest.fixture
    def rf(self):
        return RequestFactory()
