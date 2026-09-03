from django.db import models

from navi_backend.core.models import UUIDModel


class NotificationKind(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"


class NotificationCategory(models.TextChoices):
    """The topic a notification is about, independent of the channel it uses.

    User preferences are stored per (channel, category) pair, so a user can, for
    example, keep transactional order emails while muting marketing ones.
    """

    ACCOUNT = "account", "Account & security"
    ORDER_UPDATES = "order_updates", "Order updates"
    MARKETING = "marketing", "Marketing & promotions"


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
