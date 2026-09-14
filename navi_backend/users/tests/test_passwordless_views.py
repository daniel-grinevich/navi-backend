"""The request endpoints must enqueue Celery sends, never send inline."""

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

MAGIC_LINK_EXPIRES_SECONDS = 15 * 60
SMS_OTP_EXPIRES_SECONDS = 10 * 60


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class TestMagicLinkRequestView:
    @patch(
        "navi_backend.users.api.passwordless_views.send_magic_link_email.apply_async"
    )
    def test_enqueues_email_task(self, mock_apply, api_client, settings):
        response = api_client.post(
            reverse("api:magic-request"), {"email": "User@Example.com"}
        )

        assert response.status_code == 200
        mock_apply.assert_called_once()
        kwargs = mock_apply.call_args.kwargs
        email, link = kwargs["args"]
        assert email == "user@example.com"
        backend = settings.BACKEND_URL.rstrip("/")
        assert link.startswith(f"{backend}/api/auth/magic/verify/?")
        assert "token=" in link
        assert kwargs["queue"] == "email"
        assert kwargs["expires"] == MAGIC_LINK_EXPIRES_SECONDS

    @patch(
        "navi_backend.users.api.passwordless_views.send_magic_link_email.apply_async"
    )
    def test_blank_email_still_200_without_enqueue(self, mock_apply, api_client):
        response = api_client.post(reverse("api:magic-request"), {"email": ""})

        assert response.status_code == 200
        mock_apply.assert_not_called()


class TestSMSRequestView:
    @patch("navi_backend.users.api.passwordless_views.send_sms_otp.apply_async")
    def test_enqueues_sms_task(self, mock_apply, api_client):
        response = api_client.post(
            reverse("api:sms-request"), {"phone": "+1 (555) 123-4567"}
        )

        assert response.status_code == 200
        mock_apply.assert_called_once()
        kwargs = mock_apply.call_args.kwargs
        phone, message = kwargs["args"]
        assert phone == "+15551234567"
        assert "Your Navi code is" in message
        assert kwargs["expires"] == SMS_OTP_EXPIRES_SECONDS

    @patch("navi_backend.users.api.passwordless_views.send_sms_otp.apply_async")
    def test_blank_phone_still_200_without_enqueue(self, mock_apply, api_client):
        response = api_client.post(reverse("api:sms-request"), {"phone": ""})

        assert response.status_code == 200
        mock_apply.assert_not_called()
