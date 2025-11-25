import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from navi_backend.notifications.services.notifications import NotificationFactory

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_confirmation_email(self, user_id):
    try:
        user = User.objects.only("id", "email").get(pk=user_id)
    except User.DoesNotExist:
        return
    if not user.email:
        return
    service = NotificationFactory.create(
        "email", recipient=user.email, Subject="Confirm your account", body="..."
    )
    service.send()
