import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    """
    Default custom user model for Navi Backend.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    username = None
    name = models.CharField(_("Name of User"), blank=True, max_length=255)
    email = models.EmailField(_("email address"), unique=True)
    phone = models.CharField(
        _("phone number"), max_length=32, unique=True, null=True, blank=True
    )
    stripe_customer_id = models.CharField(
        max_length=255, blank=True, null=True, unique=True
    )
    email_confirmed = models.BooleanField(default=False)
    is_guest = models.BooleanField(default=False, null=False, blank=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        user_id = getattr(self, "id", None)

        if user_id is None:
            error_txt = "Cannot get_absolute_url without id."
            raise ValueError(error_txt)
        return reverse("api:users-detail", kwargs={"pk": user_id})

    def save(self, *args, **kwargs):
        if self.is_guest and not self.password:
            self.password = str(uuid.uuid4())

        super().save(*args, **kwargs)


class EmailToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} ({self.token})"


class OneTimeLogin(models.Model):
    """Single-use credential for passwordless sign-in.

    Backs both magic links (email) and SMS OTP codes. We store only a hash of
    the secret so a database leak can't be replayed. ``target`` is the email or
    phone the secret was issued to; verification must match it so a code issued
    for one identity can't be used for another.
    """

    class Purpose(models.TextChoices):
        MAGIC_LINK = "magic_link", "Magic link"
        SMS_OTP = "sms_otp", "SMS OTP"

    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    target = models.CharField(max_length=255, db_index=True)
    token_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["purpose", "target"])]

    def __str__(self):
        return f"{self.purpose}:{self.target}"

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()


class UserPreferences(models.Model):
    """Per-user settings surfaced on the frontend settings page.

    Notification toggles are keyed by (channel, category) so a user can control
    each topic independently per channel. Categories/channels are defined in
    navi_backend.notifications.models to keep a single source of truth.
    """

    class Theme(models.TextChoices):
        SYSTEM = "system", _("System")
        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="preferences",
    )

    # General preferences
    theme = models.CharField(max_length=16, choices=Theme.choices, default=Theme.SYSTEM)
    language = models.CharField(
        max_length=10,
        default="en",
        help_text=_("IETF language tag, e.g. 'en' or 'en-US'"),
    )

    # Email notification toggles (channel="email")
    email_account = models.BooleanField(default=True)
    email_order_updates = models.BooleanField(default=True)
    email_marketing = models.BooleanField(default=False)
    email_rewards = models.BooleanField(default=True)

    # SMS notification toggles (channel="sms")
    sms_account = models.BooleanField(default=True)
    sms_order_updates = models.BooleanField(default=True)
    sms_marketing = models.BooleanField(default=False)
    sms_rewards = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("user preferences")
        verbose_name_plural = _("user preferences")

    def __str__(self):
        return f"Preferences for {self.user.email}"

    def allows(self, kind: str, category: str) -> bool:
        """Return whether the user permits a notification for a channel/category.

        Unknown combinations default to True so new notification types are never
        silently dropped before a matching toggle is added here.
        """
        field = f"{kind}_{category}"
        value = getattr(self, field, None)
        if value is None:
            return True
        return bool(value)
