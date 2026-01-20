import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from navi_backend.notifications.services.notification_strategy import (
    EmailNotificationService,
)

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_confirmation_email(self, user_id):
    try:
        user = User.objects.only("id", "email", "name").get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("User %s not found for confirmation email", user_id)
        return
    if not user.email:
        logger.warning("User %s has no email address", user_id)
        return

    notification = EmailNotificationService(
        recipient=user.email,
        subject="Welcome to Navi Coffee!",
        template="emails/welcome.html",
        context={"name": getattr(user, "name", "")},
        reason="user_confirmation",
    )
    notification.send()
