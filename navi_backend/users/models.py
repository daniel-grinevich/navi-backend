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
        return reverse("users-detail", kwargs={"pk": self.id})

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
