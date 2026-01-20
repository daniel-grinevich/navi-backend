import logging
from abc import ABC
from abc import abstractmethod

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.models import TextLog

logger = logging.getLogger(__name__)


class NotificationService(ABC):
    kind: str = None

    def __init__(self, recipient, reason=""):
        self.recipient = recipient
        self.reason = reason
        self.is_sent = False
        self.error = ""

    def send(self):
        try:
            self._validate()
            self._deliver()
            self.is_sent = True
        except Exception as e:
            logger.exception(
                "Failed to send %s notification to %s", self.kind, self.recipient
            )
            self.error = str(e)
            self.is_sent = False
        finally:
            self._log()
        return self.is_sent

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


class EmailNotificationService(NotificationService):
    kind = NotificationKind.EMAIL

    def __init__(  # noqa: PLR0913
        self,
        recipient,
        subject,
        body="",
        template=None,
        context=None,
        from_email=None,
        reply_to=None,
        **kwargs,
    ):
        super().__init__(recipient, **kwargs)
        self.subject = subject
        self.body = body
        self.template = template
        self.context = context or {}
        self.from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        self.reply_to = reply_to

    def _deliver(self):
        html_content = None
        if self.template:
            html_content = render_to_string(self.template, self.context)

        email = EmailMessage(
            subject=self.subject,
            body=self.body or html_content or "",
            from_email=self.from_email,
            to=[self.recipient] if isinstance(self.recipient, str) else self.recipient,
            reply_to=[self.reply_to] if self.reply_to else None,
        )

        if html_content:
            email.content_subtype = "html"

        email.send(fail_silently=False)

    def _log(self):
        recipient_email = (
            self.recipient[0] if isinstance(self.recipient, list) else self.recipient
        )
        EmailLog.objects.create(
            recipient=recipient_email or "",
            reason=self.reason,
            error=self.error,
            is_sent=self.is_sent,
            kind=self.kind,
            meta={
                "subject": self.subject,
                "template": self.template,
            },
        )


class SMSNotificationService(NotificationService):
    kind = NotificationKind.SMS

    def __init__(self, recipient, message, **kwargs):
        super().__init__(recipient, **kwargs)
        self.message = message

    def _deliver(self):
        pass

    def _log(self):
        TextLog.objects.create(
            recipient=self.recipient or 0,
            reason=self.reason,
            error=self.error,
            is_sent=self.is_sent,
            kind=self.kind,
            meta={
                "message": self.message,
            },
        )
