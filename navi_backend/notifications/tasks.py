import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from navi_backend.notifications.services.notification_strategy import (
    EmailNotificationService,
)
from navi_backend.notifications.services.notification_strategy import PDFAttachment
from navi_backend.payments.models import Invoice

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


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_invoice_email(self, user_id, invoice_id):
    try:
        user = User.objects.only("id", "email", "name").get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("User %s has no email address", user_id)
        return

    if not user.email:
        logger.warning("User %s has no email address", user_id)
        return

    try:
        invoice = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        logger.warning("Invoice with id of %s, does not exist", invoice_id)
        return

    attachment = None
    if invoice.pdf:
        attachment = PDFAttachment(
            filename=f"invoice-{invoice.format_reference_number()}.pdf",
            pdf_bytes=invoice.pdf.read(),
        )

    notification = EmailNotificationService(
        recipient=user.email,
        subject=f"Navi order confirmation #{invoice.reference_number}",
        reason="order_invoice",
        attachment=attachment,
    )
    notification.send()
