"""Base contract for notification channels.

Concrete channels (email, SMS, …) live in their own modules and self-register
with :class:`~navi_backend.notifications.services.factory.NotificationFactory`.
Gating is centralised here so no individual sender has to remember it:
:meth:`NotificationService.send` first honours the admin's global kill switches
(``services.global_settings``), then — when a caller passes ``user`` and
``category`` — the user's own preferences.
"""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass

from navi_backend.core.logging import get_logger
from navi_backend.notifications.services.global_settings import is_globally_enabled
from navi_backend.notifications.services.preferences import should_send

logger = get_logger(__name__)

DISABLED_GLOBALLY = "disabled_globally"


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
        self.is_sent: bool | None = False
        self.error = ""
        self.skipped = False
        self.original_reason: str | None = None

    def send(self):
        if not is_globally_enabled(self.kind, self.category):
            return self._skip_disabled_globally()
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

    def _skip_disabled_globally(self):
        """Log the skip under ``reason="disabled_globally"``.

        The caller's reason moves to ``original_reason`` so the log still says
        what was suppressed (channels add it to ``meta`` via :meth:`_meta`).
        """
        self.skipped = True
        self.is_sent = None
        self.original_reason = self.reason
        self.reason = DISABLED_GLOBALLY
        logger.info(
            "notification_skipped_disabled_globally",
            kind=self.kind,
            category=self.category,
            original_reason=self.original_reason,
            recipient=self.recipient,
        )
        self._log()
        return False

    def _meta(self, **extra):
        meta = {**extra, "skipped": self.skipped}
        if self.original_reason is not None:
            meta["original_reason"] = self.original_reason
        return meta

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
