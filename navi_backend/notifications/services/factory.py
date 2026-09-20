"""Registry-based factory for notification channels.

Channels register themselves with ``@NotificationFactory.register(kind)`` when
their module is imported (see this package's ``__init__``). Callers then build a
channel by kind without importing the concrete class::

    NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient=user.email,
        subject="Hi",
        user=user,
        category=NotificationCategory.ACCOUNT,
    ).send()
"""

import logging

logger = logging.getLogger(__name__)


class NotificationFactory:
    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, kind):
        """Decorator: register a :class:`NotificationService` subclass for ``kind``."""

        def decorator(service_cls):
            cls._registry[kind] = service_cls
            return service_cls

        return decorator

    @classmethod
    def create(cls, kind, **kwargs):
        service_cls = cls._registry.get(kind)
        if service_cls is None:
            msg = f"No notification service registered for kind {kind!r}"
            raise ValueError(msg)
        return service_cls(**kwargs)

    @classmethod
    def registered_kinds(cls):
        return tuple(cls._registry)
