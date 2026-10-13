from django.db.models.signals import m2m_changed
from django.db.models.signals import post_delete
from django.db.models.signals import post_save

from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services.port_status import invalidate_port_status_cache
from navi_backend.menu.models import MenuItem

# Everything the public port status payload is built from. Pi presence
# (last_seen) is written with queryset .update(), so it bypasses these signals
# and is picked up when the short TTL lapses.
_PORT_STATUS_MODELS = (NaviPort, RaspberryPi, EspressoMachine, MachineType, MenuItem)


def bump_port_status_cache(sender, **kwargs):
    """Orphan every cached port status whenever its inputs change."""
    invalidate_port_status_cache()


for _model in _PORT_STATUS_MODELS:
    post_save.connect(
        bump_port_status_cache,
        sender=_model,
        dispatch_uid=f"port_status_cache_save_{_model.__name__}",
    )
    post_delete.connect(
        bump_port_status_cache,
        sender=_model,
        dispatch_uid=f"port_status_cache_delete_{_model.__name__}",
    )

m2m_changed.connect(
    bump_port_status_cache,
    sender=MachineType.supported_drinks.through,
    dispatch_uid="port_status_cache_supported_drinks",
)
