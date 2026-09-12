"""Email delivery channel."""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.services.base import NotificationService
from navi_backend.notifications.services.factory import NotificationFactory


@NotificationFactory.register(NotificationKind.EMAIL)
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
        attachment=None,
        **kwargs,
    ):
        super().__init__(recipient, **kwargs)
        self.subject = subject
        self.body = body
        self.template = template
        self.context = context or {}
        self.from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        self.reply_to = reply_to
        self.attachment = attachment

    def _deliver(self):
        html_content = None
        if self.template:
            html_content = render_to_string(self.template, self.context)

        email = self.create_email_object(self.attachment, html_content)

        if html_content:
            email.content_subtype = "html"

        if self.attachment:
            email.attach(
                self.attachment.filename,
                self.attachment.pdf_bytes,
                "application/pdf",
            )

        email.send(fail_silently=False)

    def create_email_object(self, has_attachment, html_content):
        to = [self.recipient] if isinstance(self.recipient, str) else self.recipient
        reply_to = [self.reply_to] if self.reply_to else None
        cls = EmailMultiAlternatives if has_attachment else EmailMessage
        return cls(
            subject=self.subject,
            body=self.body or html_content or "",
            from_email=self.from_email,
            to=to,
            reply_to=reply_to,
        )

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
                "skipped": self.skipped,
            },
        )
