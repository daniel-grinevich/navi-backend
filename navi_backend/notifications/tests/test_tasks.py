from unittest.mock import patch

from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.tasks import send_magic_link_email
from navi_backend.notifications.tasks import send_sms_otp


@patch("navi_backend.notifications.tasks.NotificationFactory")
def test_send_magic_link_email_sends_email_notification(factory):
    send_magic_link_email("a@example.com", "https://backend/verify?token=t")

    factory.create.assert_called_once_with(
        NotificationKind.EMAIL,
        recipient="a@example.com",
        subject="Your Navi sign-in link",
        template="emails/magic_link.html",
        context={"link": "https://backend/verify?token=t", "minutes": 15},
        reason="magic_link",
    )
    factory.create.return_value.send.assert_called_once_with()


@patch("navi_backend.notifications.tasks.NotificationFactory")
def test_send_sms_otp_sends_sms_notification(factory):
    send_sms_otp("+15551234567", "Your Navi code is 123456.")

    factory.create.assert_called_once_with(
        NotificationKind.SMS,
        recipient="+15551234567",
        message="Your Navi code is 123456.",
        reason="sms_otp",
    )
    factory.create.return_value.send.assert_called_once_with()
