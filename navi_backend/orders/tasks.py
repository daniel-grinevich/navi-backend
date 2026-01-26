import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from weasyprint import HTML

from navi_backend.notifications.tasks import send_invoice_email
from navi_backend.orders.models import Order
from navi_backend.payments.models import Invoice


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def create_order_invoice(self, order_id):
    logging.info("starting to create order invoice! ")
    if order_id is None:
        logging.error("Order id was None.")
        msg = "order_id cannot be None"
        raise ValueError(msg)

    order = (
        Order.objects.select_related("user", "navi_port", "payment")
        .prefetch_related("items__menu_item", "items__customizations__customization")
        .get(id=order_id)
    )

    invoice, _ = Invoice.objects.get_or_create(
        order=order,
        defaults={"created_by": order.created_by, "updated_by": order.updated_by},
    )

    logging.info(f"Created Invoice #{invoice.id}")  # NOQA: G004

    html = render_to_string(
        "invoices/order_pdf.html",
        context={"order": order, "invoice": invoice},
    )
    pdf_bytes = HTML(string=html).write_pdf()

    invoice.pdf.save(
        f"invoice-{invoice.reference_number}-order-{order.id}",
        ContentFile(pdf_bytes),
        save=True,
    )

    send_invoice_email.apply_async(args=[order.user.id, invoice.id], queue="email")
