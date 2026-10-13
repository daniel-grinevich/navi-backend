from django.conf import settings
from django.db import models

from navi_backend.core.cache import bump_version
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


NOTIFICATION_SETTINGS_CACHE_NAMESPACE = "notification_settings"

# Categories admins may never switch off globally: login links, OTPs and
# security notices must always go out.
ALWAYS_ON_CATEGORIES = frozenset({NotificationCategory.ACCOUNT})


class NotificationSettings(models.Model):
    """Singleton of global notification kill switches, editable without a deploy.

    Layered ABOVE user preferences: a disabled channel or category blocks every
    send regardless of what the user opted into. Each switch is a
    ``<channel|category>_enabled`` field so the admin form is plain checkboxes;
    categories in :data:`ALWAYS_ON_CATEGORIES` deliberately have no field.
    Read through ``services.global_settings`` (cached), not directly.
    """

    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=True)
    order_updates_enabled = models.BooleanField(default=True)
    marketing_enabled = models.BooleanField(default=True)
    rewards_enabled = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "Notification settings"
        verbose_name_plural = "Notification settings"

    def __str__(self):
        return "Notification settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        # Read on every send; orphan the cached copy so the switch is immediate.
        bump_version(NOTIFICATION_SETTINGS_CACHE_NAMESPACE)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @staticmethod
    def channel_field(kind: str) -> str:
        return f"{kind}_enabled"

    @staticmethod
    def category_field(category: str) -> str | None:
        if category in ALWAYS_ON_CATEGORIES:
            return None
        return f"{category}_enabled"

    def channel_enabled(self, kind: str) -> bool:
        return getattr(self, self.channel_field(kind), True)

    def category_enabled(self, category: str) -> bool:
        field = self.category_field(category)
        return True if field is None else getattr(self, field, True)


class NotificationSettingsChange(UUIDModel):
    """Audit trail for :class:`NotificationSettings`: who flipped what, when."""

    class Source(models.TextChoices):
        API = "api", "Admin API"
        DJANGO_ADMIN = "django_admin", "Django admin"

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=32, choices=Source.choices)
    # e.g. {"channels": {"sms": {"old": true, "new": false}}}
    changes = models.JSONField(default=dict)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"Notification settings change at {self.changed_at:%Y-%m-%d %H:%M}"
