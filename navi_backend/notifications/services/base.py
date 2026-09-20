"""Base contract for notification channels.

Concrete channels (email, SMS, …) live in their own modules and self-register
with :class:`~navi_backend.notifications.services.factory.NotificationFactory`.
Preference gating is centralised here: when a caller passes ``user`` and
``category``, :meth:`NotificationService.send` consults the user's preferences
and skips muted notifications, so no individual sender has to remember to.
"""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass

from navi_backend.core.logging import get_logger
from navi_backend.notifications.services.preferences import should_send

logger = get_logger(__name__)


@dataclass
class PDFAttachment:
    filename: str
    pdf_bytes: bytes


class NotificationService(ABC):
    kind: str | None = None

    def __init__(self, recipient, reason="", user=None, category=None):
        self.recipient = recipient
        self.reason = reason
        # When both are set, send() enforces the user's (channel, category) opt-in.
        self.user = user
        self.category = category
        self.is_sent = False
        self.error = ""
        self.skipped = False

    def send(self):
        if self._muted():
            self.skipped = True
            self.is_sent = None
            logger.info(
                "notification_skipped_opted_out",
                kind=self.kind,
                category=self.category,
                recipient=self.recipient,
            )
            self._log()
            return False
        try:
            self._validate()
            self._deliver()
            self.is_sent = True
        except Exception as e:
            logger.exception(
                "notification_send_failed",
                kind=self.kind,
                recipient=self.recipient,
            )
            self.error = str(e)
            self.is_sent = False
        finally:
            self._log()
        return bool(self.is_sent)

    def _muted(self):
        """Honour the user's per-(channel, category) preference when known."""
        if self.user is None or self.category is None or self.kind is None:
            return False
        return not should_send(self.user, self.kind, self.category)

    def _validate(self):
        if not self.recipient:
            msg = "Missing recipient"
            raise ValueError(msg)

    @abstractmethod
    def _deliver(self):
        pass

    @abstractmethod
    def _log(self):
        pass
