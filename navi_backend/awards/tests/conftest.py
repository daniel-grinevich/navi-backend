import pytest

from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.tasks import send_award_earned_email
from navi_backend.awards.tasks import send_tier_reached_email


@pytest.fixture
def loyalty_settings(db):
    settings = LoyaltySettings.load()
    settings.points_per_dollar = 1
    settings.points_per_order = 0
    settings.notifications_enabled = True
    settings.save()
    return settings


@pytest.fixture(autouse=True)
def _mute_award_notifications(monkeypatch):
    """Award/tier notifications enqueue Celery tasks; stub the broker call so
    tests never reach Redis. Individual tests can re-patch ``.delay`` to assert
    on whether a notification would have been sent.
    """
    monkeypatch.setattr(send_award_earned_email, "delay", lambda *a, **k: None)
    monkeypatch.setattr(send_tier_reached_email, "delay", lambda *a, **k: None)
