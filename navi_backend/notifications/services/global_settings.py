"""Global notification kill switches (admin-controlled, layered above user prefs).

Reads are cached (stampede-safe, versioned key bumped by
``NotificationSettings.save``) because :func:`is_globally_enabled` runs on
every send. Writes go through :func:`update_notification_settings` so every
change is audited.
"""

from django.db import transaction

from navi_backend.core.cache import get_or_set_safe
from navi_backend.core.cache import versioned_key
from navi_backend.core.logging import get_logger
from navi_backend.notifications.models import NOTIFICATION_SETTINGS_CACHE_NAMESPACE
from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.models import NotificationSettings
from navi_backend.notifications.models import NotificationSettingsChange

logger = get_logger(__name__)

SETTINGS_CACHE_TTL = 300


def get_switches() -> dict:
    """Return ``{"channels": {...}, "categories": {...}}`` booleans, cached."""
    key = versioned_key(NOTIFICATION_SETTINGS_CACHE_NAMESPACE, "switches")
    return get_or_set_safe(key, _load_switches, SETTINGS_CACHE_TTL)


def _load_switches() -> dict:
    return _switches_of(NotificationSettings.load())


def _switches_of(obj: NotificationSettings) -> dict:
    return {
        "channels": {kind: obj.channel_enabled(kind) for kind in NotificationKind},
        "categories": {
            category: obj.category_enabled(category)
            for category in NotificationCategory
        },
    }


def is_globally_enabled(kind: str | None, category: str | None) -> bool:
    """False when an admin has switched off ``kind`` or ``category``.

    A missing ``category`` only checks the channel switch.
    """
    switches = get_switches()
    if kind is not None and not switches["channels"].get(kind, True):
        return False
    if category is None:
        return True
    return switches["categories"].get(category, True)


def update_notification_settings(
    *,
    actor,
    channels: dict[str, bool] | None = None,
    categories: dict[str, bool] | None = None,
    source: str = NotificationSettingsChange.Source.API,
) -> NotificationSettings:
    """Apply the given switches, record an audit entry, return the settings.

    Callers validate keys first; disabling an always-on category raises
    ``ValueError`` as a last line of defence.
    """
    with transaction.atomic():
        NotificationSettings.load()  # ensure the row exists before locking it
        obj = NotificationSettings.objects.select_for_update().get(pk=1)
        before = _switches_of(obj)

        for kind, enabled in (channels or {}).items():
            setattr(obj, NotificationSettings.channel_field(kind), enabled)
        for category, enabled in (categories or {}).items():
            _set_category(obj, category, enabled)

        changes = _diff(before, _switches_of(obj))
        if not changes:
            return obj

        obj.updated_by = actor
        obj.save()
        record_change(actor=actor, changes=changes, source=source)
    return obj


def _set_category(obj, category, enabled):
    field = NotificationSettings.category_field(category)
    if field is not None:
        setattr(obj, field, enabled)
        return
    if not enabled:
        msg = f"{category} notifications cannot be disabled"
        raise ValueError(msg)


def _diff(before: dict, after: dict) -> dict:
    changes: dict[str, dict] = {}
    for group, values in after.items():
        for key, new in values.items():
            old = before[group][key]
            if old != new:
                changes.setdefault(group, {})[key] = {"old": old, "new": new}
    return changes


def record_change(*, actor, changes: dict, source: str) -> None:
    NotificationSettingsChange.objects.create(
        changed_by=actor,
        changes=changes,
        source=source,
    )
    logger.info(
        "notification_settings_changed",
        changed_by=getattr(actor, "pk", None),
        source=source,
        changes=changes,
    )


def diff_switches(before: NotificationSettings, after: NotificationSettings) -> dict:
    """Public diff helper for the Django admin, which saves the model itself."""
    return _diff(_switches_of(before), _switches_of(after))
