import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
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

    # SMS notification toggles (channel="sms")
    sms_account = models.BooleanField(default=True)
    sms_order_updates = models.BooleanField(default=True)
    sms_marketing = models.BooleanField(default=False)

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
