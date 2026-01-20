import logging

from celery import shared_task

from navi_backend.orders.models import Order


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_order_invoice(self, order_id):
    if order_id is None:
        logging.error("")
        msg = "order_id cannot be None"
        raise ValueError(msg)

    order = Order.objects.get(pk=order_id)

    if order is None:
        msg = "Order does not exist."
        raise ValueError(msg)
