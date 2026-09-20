"""Notification services package.

Importing this package registers every channel with the
:class:`~navi_backend.notifications.services.factory.NotificationFactory`, so
callers can simply do::

    from navi_backend.notifications.services import NotificationFactory
"""

# Import the channel modules for their registration side effects.
from navi_backend.notifications.services import email as _email  # noqa: F401
from navi_backend.notifications.services import sms as _sms  # noqa: F401
from navi_backend.notifications.services.base import NotificationService
from navi_backend.notifications.services.base import PDFAttachment
from navi_backend.notifications.services.factory import NotificationFactory
from navi_backend.notifications.services.preferences import should_send
from navi_backend.notifications.services.sms import sms_available

__all__ = [
    "NotificationFactory",
    "NotificationService",
    "PDFAttachment",
    "should_send",
    "sms_available",
]
