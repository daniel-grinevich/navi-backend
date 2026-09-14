from django.core.cache import cache
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from navi_backend.awards.models import ACHIEVEMENTS_LIST_CACHE_KEY
from navi_backend.awards.models import PROMOTIONS_CACHE_NAMESPACE
from navi_backend.awards.models import REWARDS_CACHE_NAMESPACE
from navi_backend.awards.models import Award
from navi_backend.awards.models import AwardLevel
from navi_backend.awards.models import Promotion
from navi_backend.awards.models import Reward
from navi_backend.core.cache import bump_version


@receiver(post_save, sender=Award)
@receiver(post_delete, sender=Award)
@receiver(post_save, sender=AwardLevel)
@receiver(post_delete, sender=AwardLevel)
def invalidate_achievements_list(sender, **kwargs):
    """Drop the cached achievements catalogue whenever an award changes."""
    cache.delete(ACHIEVEMENTS_LIST_CACHE_KEY)


@receiver(post_save, sender=Reward)
@receiver(post_delete, sender=Reward)
def invalidate_rewards_list(sender, **kwargs):
    """Orphan every cached live-rewards list (soft deletes are saves too)."""
    bump_version(REWARDS_CACHE_NAMESPACE)


@receiver(post_save, sender=Promotion)
@receiver(post_delete, sender=Promotion)
def invalidate_promotions_list(sender, **kwargs):
    bump_version(PROMOTIONS_CACHE_NAMESPACE)
