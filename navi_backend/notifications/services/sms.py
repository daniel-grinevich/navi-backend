"""SMS delivery channel with a pluggable backend.

The default backend just logs to the console so SMS is a no-op in dev. A real
provider (Twilio) is selected by setting ``SMS_BACKEND = "twilio"`` and is
imported lazily so twilio stays an optional dependency. ``sms_available()``
reports whether a real (non-console) backend is configured — the preferences
API uses it so the frontend only shows SMS toggles once SMS actually sends.
"""

import logging
from abc import ABC
from abc import abstractmethod

from django.conf import settings

from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.models import TextLog
from navi_backend.notifications.services.base import NotificationService
from navi_backend.notifications.services.factory import NotificationFactory

logger = logging.getLogger(__name__)


class SMSBackend(ABC):
    @abstractmethod
    def send(self, recipient, message):
        pass


class ConsoleSMSBackend(SMSBackend):
    """Dev/default backend: logs the message instead of sending it."""

    def send(self, recipient, message):
        logger.info("[SMS console] to %s: %s", recipient, message)


class TwilioSMSBackend(SMSBackend):
    """Real delivery via Twilio. ``twilio`` is imported lazily so it stays optional."""

    def send(self, recipient, message):
        from twilio.rest import Client  # noqa: PLC0415  lazy, optional dependency

        client = Client(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
        )
        client.messages.create(
            to=str(recipient),
            from_=settings.TWILIO_FROM_NUMBER,
            body=message,
        )


_BACKENDS = {
    "console": ConsoleSMSBackend,
    "twilio": TwilioSMSBackend,
}


def _backend_name():
    return getattr(settings, "SMS_BACKEND", "console") or "console"


def get_sms_backend():
    return _BACKENDS.get(_backend_name(), ConsoleSMSBackend)()


def sms_available():
    """True when a real (non-console) SMS backend is configured."""
    return _backend_name() not in ("", "console")


@NotificationFactory.register(NotificationKind.SMS)
class SMSNotificationService(NotificationService):
    kind = NotificationKind.SMS

    def __init__(self, recipient, message, **kwargs):
        super().__init__(recipient, **kwargs)
        self.message = message

    def _deliver(self):
        get_sms_backend().send(self.recipient, self.message)

    def _log(self):
        TextLog.objects.create(
            recipient=self.recipient or 0,
            reason=self.reason,
            error=self.error,
            is_sent=self.is_sent,
            kind=self.kind,
            meta={
                "message": self.message,
                "skipped": self.skipped,
            },
        )
