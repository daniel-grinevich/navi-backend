# myapp/signals.py
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from navi_backend.notifications.tasks import send_user_confirmation_email
from navi_backend.users.models import UserPreferences


@receiver(post_save, sender=get_user_model())
def send_confirmation_on_create(sender, instance, created, **kwargs):
    if not created:
        return

    send_user_confirmation_email.delay(user_id=instance.pk)


@receiver(post_save, sender=get_user_model())
def create_user_preferences(sender, instance, created, **kwargs):
    if not created:
        return

    UserPreferences.objects.get_or_create(user=instance)
