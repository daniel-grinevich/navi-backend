from django.conf import settings
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
    REWARDS = "rewards", "Rewards & loyalty"


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
    # Phone numbers are stored as text: they can start with "+", keep leading
    # zeros, and exceed a 32-bit integer's range, so IntegerField can't hold them.
    recipient = models.CharField(max_length=32, null=False, blank=False)

    def __str__(self):
        return f"Text to {self.recipient} - {self.kind}"


class EmailTemplate(UUIDModel):
    subject = models.CharField(max_length=255)
    body = models.TextField()
    link = models.URLField()

    # Admin-authored records: TrackUserMixin stamps who created/edited them.
    # Nullable so system/data-migration inserts don't require a user context.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_emailtemplate_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_emailtemplate_updated",
    )

    def __str__(self):
        return self.subject
