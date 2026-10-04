"""Tests for the Prometheus /metrics endpoint."""

import pytest

# ATOMIC_REQUESTS wraps every request in a transaction, so even these
# DB-free views need database access enabled.
pytestmark = pytest.mark.django_db

POD_IP = "10.42.1.22"
POD_HOST = f"{POD_IP}:5000"


@pytest.fixture
def in_cluster(settings):
    settings.DEBUG = False
    settings.POD_IP = POD_IP
    settings.ALLOWED_HOSTS = [POD_IP, "api.navitascoffee.com"]


@pytest.mark.usefixtures("in_cluster")
class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_prometheus_text(self, client):
        response = client.get("/metrics", HTTP_HOST=POD_HOST)
        assert response.status_code == 200
        assert "# HELP" in response.content.decode()

    def test_http_request_metrics_are_recorded(self, client):
        client.get("/health/", HTTP_HOST=POD_HOST)
        body = client.get("/metrics", HTTP_HOST=POD_HOST).content.decode()
        assert "django_http_requests_total_by_method_total" in body
        assert 'method="GET"' in body

    def test_public_host_gets_404(self, client):
        # Cloudflare routes every path on api.navitascoffee.com to the pod.
        response = client.get("/metrics", HTTP_HOST="api.navitascoffee.com")
        assert response.status_code == 404

    def test_404_when_pod_ip_unset(self, client, settings):
        settings.POD_IP = ""
        assert client.get("/metrics", HTTP_HOST=POD_HOST).status_code == 404
