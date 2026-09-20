from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction

from navi_backend.awards.models import Award
from navi_backend.awards.models import AwardLevel
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services import points_service
from navi_backend.awards.services.rules import invalidate_user_metrics
from navi_backend.core.logging import get_logger
from navi_backend.notifications.models import NotificationCategory
from navi_backend.notifications.models import NotificationKind
from navi_backend.notifications.services import NotificationFactory
from navi_backend.orders.models import Order

logger = get_logger(__name__)

User = get_user_model()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_order_awards(self, order_id):
    """Grant points and evaluate awards/tiers for a completed order."""
    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("awards_order_not_found", order_id=order_id)
        return

    points_service.process_order(order)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def evaluate_user_awards(self, user_id):
    """Re-evaluate awards and tier for a user after any qualifying event.

    Generic counterpart to ``process_order_awards``: enqueue this from any
    place a user does something award-relevant that isn't an order (writing a
    review, completing a profile, ...). Idempotent — already-earned awards and
    levels are skipped.
    """
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("awards_user_not_found", user_id=user_id)
        return

    invalidate_user_metrics(user.id)
    with transaction.atomic():
        loyalty = UserLoyalty.for_user(user)
        points_service.evaluate_awards(loyalty)
        points_service.recompute_tier(loyalty)


def _loyalty_notifications_on():
    """Program-wide kill-switch. Per-user opt-in is handled by the factory via
    the user's ``rewards`` notification preference."""
    return LoyaltySettings.load().notifications_enabled


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_award_earned_email(self, user_id, award_id, level_id=None):
    try:
        user = (
            User.objects.select_related("preferences")
            .only("id", "email", "name")
            .get(pk=user_id)
        )
    except User.DoesNotExist:
        logger.warning("award_email_user_not_found", user_id=user_id)
        return
    if not user.email:
        logger.warning("award_email_user_no_email", user_id=user_id)
        return

    # Re-check the program-wide kill-switch at send time; the user's own opt-in
    # (rewards preference) is enforced by the factory below.
    if not _loyalty_notifications_on():
        return

    try:
        award = Award.objects.get(pk=award_id)
    except Award.DoesNotExist:
        logger.warning("award_email_award_not_found", award_id=award_id)
        return

    level = None
    if level_id:
        level = AwardLevel.objects.filter(pk=level_id).first()

    badge_name = f"{award.name} — {level.name}" if level else award.name
    notification = NotificationFactory.create(
        NotificationKind.EMAIL,
        recipient=user.email,
        subject=f"You earned the {badge_name} badge! 🎉",
        template="emails/award_earned.html",
        context={
            "name": getattr(user, "name", ""),
            "award_name": badge_name,
            "award_description": award.description,
            "points_reward": level.points_reward if level else award.points_reward,
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
        logger.warning("tier_email_user_not_found", user_id=user_id)
        return
    if not user.email:
        logger.warning("tier_email_user_no_email", user_id=user_id)
        return

    if not _loyalty_notifications_on():
        return

    try:
        tier = Tier.objects.get(pk=tier_id)
    except Tier.DoesNotExist:
        logger.warning("tier_email_tier_not_found", tier_id=tier_id)
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
