"""Tests for the Prometheus /metrics endpoint."""

import pytest

# ATOMIC_REQUESTS wraps every request in a transaction, so even these
# DB-free views need database access enabled.
pytestmark = pytest.mark.django_db


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_prometheus_text(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "# HELP" in response.content.decode()

    def test_http_request_metrics_are_recorded(self, client):
        client.get("/health/")
        body = client.get("/metrics").content.decode()
        assert "django_http_requests_total_by_method_total" in body
        assert 'method="GET"' in body
