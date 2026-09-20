"""Backwards-compatible re-exports.

The notification services were split into ``base`` / ``factory`` / ``email`` /
``sms`` modules. Import from :mod:`navi_backend.notifications.services` (which
exposes ``NotificationFactory``) or the specific channel module going forward.
This shim keeps older ``from ...notification_strategy import X`` imports working.
"""

from navi_backend.notifications.services.base import NotificationService
from navi_backend.notifications.services.base import PDFAttachment
from navi_backend.notifications.services.email import EmailNotificationService
from navi_backend.notifications.services.sms import SMSNotificationService

__all__ = [
    "EmailNotificationService",
    "NotificationService",
    "PDFAttachment",
    "SMSNotificationService",
]
