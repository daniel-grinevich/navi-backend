from django.core.cache import cache
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from navi_backend.awards.models import ACHIEVEMENTS_LIST_CACHE_KEY
from navi_backend.awards.models import Award
from navi_backend.awards.models import AwardLevel


@receiver(post_save, sender=Award)
@receiver(post_delete, sender=Award)
@receiver(post_save, sender=AwardLevel)
@receiver(post_delete, sender=AwardLevel)
def invalidate_achievements_list(sender, **kwargs):
    """Drop the cached achievements catalogue whenever an award changes."""
    cache.delete(ACHIEVEMENTS_LIST_CACHE_KEY)
