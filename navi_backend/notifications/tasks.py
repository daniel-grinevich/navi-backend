import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.services import NotificationFactory
from navi_backend.notifications.services import PDFAttachment
from navi_backend.payments.models import Invoice

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_user_confirmation_email(self, user_id):
    try:
        user = (
            User.objects.select_related("preferences")
            .only("id", "email", "name")
            .get(pk=user_id)
        )
    except User.DoesNotExist:
        logger.warning("User %s not found for confirmation email", user_id)
        return
    if not user.email:
        logger.warning("User %s has no email address: ", user_id)
        return

    # Opt-in is enforced centrally by the factory via user + category.
    notification = NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient=user.email,
        subject="Welcome to Navi Coffee!",
        template="emails/welcome.html",
        context={"name": getattr(user, "name", "")},
        reason="user_confirmation",
        user=user,
        category=NotificationCategory.ACCOUNT,
    )
    notification.send()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_invoice_email(self, user_id, invoice_id):
    try:
        user = (
            User.objects.select_related("preferences")
            .only("id", "email", "name")
            .get(pk=user_id)
        )
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

    notification = NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient=user.email,
        subject=f"Navi order confirmation #{invoice.reference_number}",
        reason="order_invoice",
        attachment=attachment,
        user=user,
        category=NotificationCategory.ORDER_UPDATES,
    )
    notification.send()
