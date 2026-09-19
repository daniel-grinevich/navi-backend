from celery import shared_task
from django.contrib.auth import get_user_model

from navi_backend.core.logging import get_logger
from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.services import NotificationFactory
from navi_backend.notifications.services import PDFAttachment
from navi_backend.payments.models import Invoice

logger = get_logger(__name__)

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
        logger.warning("confirmation_email_user_not_found", user_id=user_id)
        return
    if not user.email:
        logger.warning("confirmation_email_user_no_email", user_id=user_id)
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


# Low retry cap: the magic-link token expires in 15 minutes, so retrying
# for longer would deliver a dead link. Callers also set ``expires`` so a
# backed-up queue drops the send instead of delivering it late.
@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_magic_link_email(self, email, link):
    NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient=email,
        subject="Your Navi sign-in link",
        template="emails/magic_link.html",
        context={"link": link, "minutes": 15},
        reason="magic_link",
    ).send()


# Same reasoning as the magic link: the OTP expires in 10 minutes.
@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_sms_otp(self, phone, message):
    NotificationFactory.create(
        NotificationKind.SMS,
        recipient=phone,
        message=message,
        reason="sms_otp",
    ).send()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_invoice_email(self, user_id, invoice_id):
    try:
        user = (
            User.objects.select_related("preferences")
            .only("id", "email", "name")
            .get(pk=user_id)
        )
    except User.DoesNotExist:
        logger.warning("invoice_email_user_not_found", user_id=user_id)
        return

    if not user.email:
        logger.warning("invoice_email_user_no_email", user_id=user_id)
        return

    try:
        invoice = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        logger.warning("invoice_email_invoice_not_found", invoice_id=invoice_id)
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
