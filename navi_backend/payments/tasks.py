from celery import shared_task
from django.utils import timezone

from navi_backend.core.logging import get_logger
from navi_backend.devices.models import NaviPort
from navi_backend.payments.models import EffectiveTaxRate
from navi_backend.payments.services import StripePaymentService
from navi_backend.payments.taxjar import fetch_combined_rate

logger = get_logger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def cancel_stripe_setup_intent(self, setup_intent_id):
    """Cancel a checkout SetupIntent out of the request path."""
    StripePaymentService.cancel_setup_intent(setup_intent_id)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def record_stripe_tax_transaction(self, order_id):
    """Record a completed sale to Stripe Tax for filing (off the scan path)."""
    StripePaymentService.record_tax_transaction(order_id)


@shared_task
def refresh_effective_tax_rates():
    """Nightly: refresh each NaviPort's cached jurisdiction tax rate from TaxJar.

    A failed lookup for one port is logged and skipped so the last known rate is
    kept rather than overwritten with a bad value; other ports still refresh.
    """
    today = timezone.localdate()
    updated = 0

    for navi_port in NaviPort.objects.all():
        try:
            rate = fetch_combined_rate(navi_port)
        except Exception:
            logger.exception("Tax rate lookup failed for NaviPort %s", navi_port.pk)
            continue

        if rate is None:
            logger.warning("No tax rate returned for NaviPort %s", navi_port.pk)
            continue

        EffectiveTaxRate.objects.update_or_create(
            navi_port=navi_port,
            effective_date=today,
            defaults={"rate": rate},
        )
        updated += 1

    logger.info("Refreshed effective tax rates for %s NaviPort(s)", updated)
    return updated
