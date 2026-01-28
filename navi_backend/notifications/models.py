from django.db import models

from navi_backend.core.models import UUIDModel


class NotificationKind(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"


class NotificationLog(UUIDModel):
    reason = models.CharField(max_length=50, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    error = models.TextField(blank=True)
    meta = models.JSONField(null=True, blank=True)
    is_sent = models.BooleanField(null=True, blank=True)

    kind = models.CharField(
        max_length=32,
        choices=NotificationKind.choices,
        help_text="Where or what subsystem emitted this log",
    )

    class Meta:
        abstract = True


class EmailLog(NotificationLog):
    recipient = models.EmailField(null=False, blank=False)

    def __str__(self):
        return f"Email to {self.recipient} - {self.kind}"


class TextLog(NotificationLog):
    recipient = models.IntegerField(max_length=10, null=False, blank=False)

    def __str__(self):
        return f"Text to {self.recipient} - {self.kind}"


class EmailTemplate(UUIDModel):
    subject = models.CharField(max_length=255)
    body = models.TextField()
    link = models.URLField()

    def __str__(self):
        return self.subject
