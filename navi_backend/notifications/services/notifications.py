import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from navi_backend.notifications.models import EmailLog
from navi_backend.notifications.models import EmailTemplate


class Notification:
    suppress = False  # class-level flag

    def __init__(self, recipient=None, error=""):
        self.recipient = recipient
        self.is_sent = False
        self.error = error

    def send(self, **kwargs):
        raise NotImplementedError

    def log(self):
        raise NotImplementedError

    @classmethod
    def set_suppression(cls, is_suppress):
        cls.suppress = is_suppress


class TextNotification(Notification):
    def __init__(self, recipient=None, img_caption=""):
        super().__init__(recipient=recipient)
        self.img_caption = img_caption

    def send(self, **kwargs):
        if self.suppress:
            return
        # Implement SMS provider here
        self.is_sent = True

    def log(self):
        # Implement a TextLog if you have one
        pass


class EmailNotification(Notification):
    def __init__(
        self, recipient=None, subject="", body="", event=None, from_email=None, **kwargs
    ):
        super().__init__(recipient=recipient)
        self.subject = subject
        self.body = body
        self.event = event  # e.g., template key/slug
        self.from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        self.context = dict(kwargs)

    def send(self, **kwargs):
        try:
            if self.suppress:
                return

            if not self.recipient:
                self.error = "Missing recipient"
                self.is_sent = False
                return

            subject = self.subject
            body = self.body

            if self.event:
                try:
                    tpl = EmailTemplate.objects.get(event=self.event)
                except EmailTemplate.DoesNotExist:
                    self.error = f"EmailTemplate not found for event={self.event}"
                    self.is_sent = False
                    return
                subject = tpl.subject or subject
                body = tpl.body or body

            send_mail(
                subject=subject,
                message=body,
                from_email=self.from_email,
                recipient_list=[self.recipient],
                fail_silently=False,
            )
            self.is_sent = True

        except smtplib.SMTPException as e:
            self.error = str(e)
            self.is_sent = False
        finally:
            self.log()

    def log(self):
        EmailLog.objects.create(
            recipient=self.recipient or "",
            error=self.error or "",
            sent_at=timezone.now(),
            is_sent=self.is_sent,
            meta=self.context,
        )


class NotificationFactory:
    _registry = {}
    kind = None  # subclasses set this, e.g., "email", "text"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        kind = getattr(cls, "kind", None)
        if cls is not NotificationFactory and kind:
            NotificationFactory._registry[kind] = cls

    @classmethod
    def create(cls, kind, **kwargs):
        try:
            factory_cls = cls._registry[kind]
        except KeyError as e:
            msg = f"No factory registered for kind={kind!r}"
            raise RuntimeError(msg) from e
        return factory_cls.create_notification(**kwargs)

    @classmethod
    def create_notification(cls, **kwargs):
        raise NotImplementedError


class TextFactory(NotificationFactory):
    kind = "text"

    @classmethod
    def create_notification(cls, **kwargs):
        return TextNotification(**kwargs)


class EmailFactory(NotificationFactory):
    kind = "email"

    @classmethod
    def create_notification(cls, **kwargs):
        return EmailNotification(**kwargs)
