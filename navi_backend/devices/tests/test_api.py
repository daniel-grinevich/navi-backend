"""NaviPort API: public reads, staff-only writes (audit S1)."""

import pytest
from rest_framework.test import APIClient

from navi_backend.devices.models import NaviPort
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def navi_port():
    return NaviPortFactory(postal_code="10001")


def _detail(navi_port):
    return f"/api/navi_ports/{navi_port.pk}/"


class TestNaviPortReads:
    def test_anonymous_can_list(self, api_client, navi_port):
        resp = api_client.get("/api/navi_ports/")
        assert resp.status_code == 200

    def test_anonymous_can_retrieve(self, api_client, navi_port):
        resp = api_client.get(_detail(navi_port))
        assert resp.status_code == 200


class TestNaviPortWrites:
    def test_plain_user_cannot_patch(self, api_client, navi_port):
        api_client.force_authenticate(user=UserFactory())

        resp = api_client.patch(
            _detail(navi_port), {"postal_code": "94105"}, format="json"
        )

        assert resp.status_code == 403
        navi_port.refresh_from_db()
        assert navi_port.postal_code == "10001"

    def test_plain_user_cannot_delete(self, api_client, navi_port):
        api_client.force_authenticate(user=UserFactory())

        resp = api_client.delete(_detail(navi_port))

        assert resp.status_code == 403
        assert NaviPort.objects.filter(pk=navi_port.pk).exists()

    def test_plain_user_cannot_create(self, api_client):
        api_client.force_authenticate(user=UserFactory())

        resp = api_client.post("/api/navi_ports/", {"name": "x"}, format="json")

        assert resp.status_code == 403

    def test_anonymous_cannot_patch(self, api_client, navi_port):
        resp = api_client.patch(
            _detail(navi_port), {"postal_code": "94105"}, format="json"
        )
        assert resp.status_code in (401, 403)

    def test_staff_can_patch(self, api_client, navi_port, admin_user):
        api_client.force_authenticate(user=admin_user)

        resp = api_client.patch(
            _detail(navi_port), {"postal_code": "94105"}, format="json"
        )

        assert resp.status_code == 200
        navi_port.refresh_from_db()
        assert navi_port.postal_code == "94105"

    def test_staff_can_delete(self, api_client, navi_port, admin_user):
        api_client.force_authenticate(user=admin_user)

        resp = api_client.delete(_detail(navi_port))

        assert resp.status_code == 204
