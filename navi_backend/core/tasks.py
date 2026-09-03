import logging

from celery import shared_task
from django.apps import apps

from navi_backend.core.helpers.geo_cache import geocode_address_fields

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def populate_address_from_geo(self, app_label, model_name, pk):
    """Reverse-geocode an ``AddressModel`` row and fill in its address fields.

    Runs outside the request path so the write that created the row never blocks
    on the external geocoder. Safe to retry; writes with ``queryset.update`` so
    it never re-triggers ``save()`` (and thus never re-dispatches itself).
    """
    model = apps.get_model(app_label, model_name)
    obj = (
        model.objects.filter(pk=pk)
        .only("pk", "latitude", "longitude", "country")
        .first()
    )
    if obj is None:
        logger.warning("%s.%s %s not found for geocoding", app_label, model_name, pk)
        return

    if obj.latitude is None or obj.longitude is None:
        return

    fields = geocode_address_fields(obj.latitude, obj.longitude)
    # Respect a country that was set explicitly on the row.
    if obj.country:
        fields.pop("country", None)

    model.objects.filter(pk=pk).update(**fields)
