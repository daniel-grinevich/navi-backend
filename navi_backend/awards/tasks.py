import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from navi_backend.awards.models import Award
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import Tier
from navi_backend.awards.services import points_service
from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.services import NotificationFactory
from navi_backend.orders.models import Order

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_order_awards(self, order_id):
    """Grant points and evaluate awards/tiers for a completed order."""
    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("Order %s not found for awards processing", order_id)
        return

    points_service.process_order(order)


def _loyalty_notifications_on():
    """Program-wide kill-switch. Per-user opt-in is handled by the factory via
    the user's ``rewards`` notification preference."""
    return LoyaltySettings.load().notifications_enabled


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_award_earned_email(self, user_id, award_id):
    try:
        user = (
            User.objects.select_related("preferences")
            .only("id", "email", "name")
            .get(pk=user_id)
        )
    except User.DoesNotExist:
        logger.warning("User %s not found for award email", user_id)
        return
    if not user.email:
        logger.warning("User %s has no email address for award email", user_id)
        return

    # Re-check the program-wide kill-switch at send time; the user's own opt-in
    # (rewards preference) is enforced by the factory below.
    if not _loyalty_notifications_on():
        return

    try:
        award = Award.objects.get(pk=award_id)
    except Award.DoesNotExist:
        logger.warning("Award %s not found for award email", award_id)
        return

    notification = NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient=user.email,
        subject=f"You earned the {award.name} award! 🎉",
        template="emails/award_earned.html",
        context={
            "name": getattr(user, "name", ""),
            "award_name": award.name,
            "award_description": award.description,
            "points_reward": award.points_reward,
        },
        reason="award_earned",
        user=user,
        category=NotificationCategory.REWARDS,
    )
    notification.send()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_tier_reached_email(self, user_id, tier_id):
    try:
        user = (
            User.objects.select_related("preferences")
            .only("id", "email", "name")
            .get(pk=user_id)
        )
    except User.DoesNotExist:
        logger.warning("User %s not found for tier email", user_id)
        return
    if not user.email:
        logger.warning("User %s has no email address for tier email", user_id)
        return

    if not _loyalty_notifications_on():
        return

    try:
        tier = Tier.objects.get(pk=tier_id)
    except Tier.DoesNotExist:
        logger.warning("Tier %s not found for tier email", tier_id)
        return

    notification = NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient=user.email,
        subject=f"You reached {tier.name}! 🎉",
        template="emails/tier_reached.html",
        context={
            "name": getattr(user, "name", ""),
            "tier_name": tier.name,
            "tier_benefits": tier.benefits,
        },
        reason="tier_reached",
        user=user,
        category=NotificationCategory.REWARDS,
    )
    notification.send()
