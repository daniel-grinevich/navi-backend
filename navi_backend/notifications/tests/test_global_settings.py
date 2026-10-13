import pytest
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.models import NotificationSettings
from navi_backend.notifications.models import NotificationSettingsChange
from navi_backend.notifications.models import TextLog
from navi_backend.notifications.services import NotificationFactory
from navi_backend.notifications.services.global_settings import get_switches
from navi_backend.notifications.services.global_settings import (
    update_notification_settings,
)
from navi_backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

URL = reverse("api:admin-notification-settings")


@pytest.fixture
def staff():
    return UserFactory(is_staff=True, email="admin@navi.coffee")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def staff_client(api_client, staff):
    api_client.force_authenticate(user=staff)
    return api_client


def _email(category=None, user=None, reason="test_email"):
    return NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient="customer@example.com",
        subject="Hello",
        body="Hi",
        reason=reason,
        user=user,
        category=category,
    )


def _sms(category=None, reason="test_sms"):
    return NotificationFactory.create(
        NotificationKind.SMS,
        recipient="+15551234567",
        message="Hi",
        reason=reason,
        category=category,
    )


class TestKillSwitchEnforcement:
    def test_everything_sends_by_default(self):
        assert _email(NotificationCategory.MARKETING).send() is True
        assert _sms(NotificationCategory.MARKETING).send() is True
        assert len(mail.outbox) == 1

    def test_disabled_email_channel_blocks_and_logs_skip(self, staff):
        update_notification_settings(actor=staff, channels={"email": False})

        assert (
            _email(NotificationCategory.ORDER_UPDATES, reason="invoice").send() is False
        )

        assert mail.outbox == []
        log = EmailLog.objects.get()
        assert log.reason == "disabled_globally"
        assert log.is_sent is None
        assert log.meta["skipped"] is True
        assert log.meta["original_reason"] == "invoice"

    def test_disabled_sms_channel_blocks_and_logs_skip(self, staff):
        update_notification_settings(actor=staff, channels={"sms": False})

        assert _sms(reason="sms_otp").send() is False

        log = TextLog.objects.get()
        assert log.reason == "disabled_globally"
        assert log.is_sent is None
        assert log.meta["original_reason"] == "sms_otp"

    def test_disabled_channel_blocks_sends_without_a_category(self, staff):
        update_notification_settings(actor=staff, channels={"email": False})

        assert _email(category=None).send() is False
        assert mail.outbox == []

    def test_disabling_one_channel_leaves_the_other(self, staff):
        update_notification_settings(actor=staff, channels={"sms": False})

        assert _email(NotificationCategory.ORDER_UPDATES).send() is True
        assert len(mail.outbox) == 1

    @pytest.mark.parametrize(
        "category",
        [
            NotificationCategory.ORDER_UPDATES,
            NotificationCategory.MARKETING,
            NotificationCategory.REWARDS,
        ],
    )
    @pytest.mark.parametrize("make", [_email, _sms])
    def test_disabled_category_blocks_every_channel(self, staff, category, make):
        update_notification_settings(actor=staff, categories={category: False})

        assert make(category).send() is False

        log_model = EmailLog if make is _email else TextLog
        assert log_model.objects.get().reason == "disabled_globally"

    def test_disabled_category_leaves_other_categories(self, staff):
        update_notification_settings(actor=staff, categories={"marketing": False})

        assert _email(NotificationCategory.ORDER_UPDATES).send() is True
        assert _email(category=None).send() is True
        assert len(mail.outbox) == 2

    def test_account_still_sends_with_every_other_category_off(self, staff):
        update_notification_settings(
            actor=staff,
            categories={"order_updates": False, "marketing": False, "rewards": False},
        )

        assert _email(NotificationCategory.ACCOUNT).send() is True

    def test_global_switch_overrides_user_opt_in(self, staff):
        user = UserFactory()
        update_notification_settings(actor=staff, categories={"rewards": False})

        assert _email(NotificationCategory.REWARDS, user=user).send() is False
        assert mail.outbox == []

    def test_reenabling_resumes_sending(self, staff):
        update_notification_settings(actor=staff, channels={"email": False})
        update_notification_settings(actor=staff, channels={"email": True})

        assert _email().send() is True


class TestService:
    def test_account_category_cannot_be_disabled(self, staff):
        with pytest.raises(ValueError, match="cannot be disabled"):
            update_notification_settings(actor=staff, categories={"account": False})

        assert NotificationSettingsChange.objects.count() == 0

    def test_change_is_audited(self, staff):
        update_notification_settings(
            actor=staff,
            channels={"sms": False, "email": True},
            categories={"marketing": False},
        )

        change = NotificationSettingsChange.objects.get()
        assert change.changed_by == staff
        assert change.source == NotificationSettingsChange.Source.API
        # Only real flips are recorded (email was already on).
        assert change.changes == {
            "channels": {"sms": {"old": True, "new": False}},
            "categories": {"marketing": {"old": True, "new": False}},
        }
        assert NotificationSettings.load().updated_by == staff

    def test_noop_update_is_not_audited(self, staff):
        update_notification_settings(actor=staff, channels={"email": True})

        assert NotificationSettingsChange.objects.count() == 0

    def test_save_invalidates_cached_switches(self, settings, staff):
        settings.CACHES = {
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        }
        cache.clear()
        assert get_switches()["channels"]["email"] is True

        update_notification_settings(actor=staff, channels={"email": False})

        assert get_switches()["channels"]["email"] is False
        cache.clear()


class TestAPI:
    def test_unauthenticated_is_401(self, api_client):
        assert api_client.get(URL).status_code == 401
        assert api_client.patch(URL, {}, format="json").status_code == 401

    def test_non_staff_is_403(self, api_client):
        api_client.force_authenticate(user=UserFactory())

        assert api_client.get(URL).status_code == 403
        response = api_client.patch(URL, {"channels": {"email": False}}, format="json")
        assert response.status_code == 403
        assert NotificationSettings.load().email_enabled is True

    def test_get_returns_contract_shape(self, staff_client):
        response = staff_client.get(URL)

        assert response.status_code == 200
        body = response.json()
        assert body["channels"] == {"email": True, "sms": True}
        assert body["categories"] == {
            "account": True,
            "order_updates": True,
            "marketing": True,
            "rewards": True,
        }
        assert body["updated_by"] is None
        assert body["updated_at"]

    def test_patch_subset(self, staff_client):
        response = staff_client.patch(URL, {"channels": {"sms": False}}, format="json")

        assert response.status_code == 200
        body = response.json()
        assert body["channels"] == {"email": True, "sms": False}
        assert body["categories"]["marketing"] is True
        assert body["updated_by"] == "admin@navi.coffee"

        response = staff_client.patch(
            URL,
            {"categories": {"marketing": False}},
            format="json",
        )
        assert response.json()["channels"]["sms"] is False
        assert response.json()["categories"]["marketing"] is False
        assert NotificationSettingsChange.objects.count() == 2

    def test_patch_account_false_is_400(self, staff_client):
        response = staff_client.patch(
            URL,
            {"categories": {"account": False}},
            format="json",
        )

        assert response.status_code == 400
        # The project-wide exception handler wraps errors in {"error": {...}}.
        assert response.json()["error"]["message"] == {
            "categories": ["account notifications cannot be disabled"],
        }

    def test_patch_account_true_is_allowed(self, staff_client):
        response = staff_client.patch(
            URL,
            {"categories": {"account": True}},
            format="json",
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "payload",
        [{"channels": {"pigeon": False}}, {"categories": {"spam": False}}],
    )
    def test_patch_unknown_key_is_400(self, staff_client, payload):
        response = staff_client.patch(URL, payload, format="json")

        assert response.status_code == 400
        assert next(iter(payload)) in response.json()["error"]["message"]
        assert NotificationSettingsChange.objects.count() == 0
