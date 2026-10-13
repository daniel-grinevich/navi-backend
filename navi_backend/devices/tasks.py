from celery import shared_task
from django.conf import settings

from navi_backend.core.logging import get_logger
from navi_backend.devices.models import DeviceEvent

logger = get_logger(__name__)


@shared_task
def purge_old_device_events(days: int | None = None) -> int:
    """Delete device events older than the retention window."""
    days = days or settings.DEVICE_EVENT_RETENTION_DAYS
    deleted, _ = DeviceEvent.objects.older_than(days).delete()
    logger.info("device_events_purged", deleted=deleted, retention_days=days)
    return deleted
