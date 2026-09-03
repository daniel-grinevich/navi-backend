"""Helpers for honouring a user's notification preferences before sending.

Kept separate from the delivery strategies so any caller (Celery tasks, views,
future channels) can ask "is this user opted in?" without importing the users
app's models directly.
"""

import logging

logger = logging.getLogger(__name__)


def should_send(user, kind: str, category: str) -> bool:
    """Return whether ``user`` wants a ``kind``/``category`` notification.

    ``kind`` is a :class:`~navi_backend.notifications.models.NotificationKind`
    value (e.g. ``"email"``) and ``category`` a
    :class:`~navi_backend.notifications.models.NotificationCategory` value.

    Defaults to ``True`` when the user has no preferences row yet so that a
    misconfiguration never silently swallows a notification.
    """
    prefs = getattr(user, "preferences", None)
    if prefs is None:
        return True
    return prefs.allows(kind, category)
