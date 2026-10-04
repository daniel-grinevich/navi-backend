"""Plain Django views for internal endpoints."""

from django.conf import settings
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django_prometheus.exports import ExportToDjangoView


def internal_metrics(request: HttpRequest) -> HttpResponse:
    """Prometheus metrics, only for in-cluster scrapes.

    Prometheus scrapes the pod by IP; public traffic arrives through the
    Cloudflare tunnel as api.navitascoffee.com. Anything not addressed to this
    pod's IP gets a 404 (DEBUG keeps it open for local development).
    """
    host = request.get_host().rsplit(":", 1)[0]
    if not settings.DEBUG and host != settings.POD_IP:
        raise Http404
    return ExportToDjangoView(request)
