from django.core.cache import cache
from django.db import models
from django.utils import timezone


class MenuItemManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(status="A")

    def featured(self):
        return self.active().filter(is_featured=True)

    def by_category(self, category_slug):
        return self.active().filter(category__slug=category_slug)

    def most_viewed(self, limit=30):
        return self.active().order_by("-selected_count")[:limit]

    def most_selected(self, limit=30):
        return self.active().order_by("-selected_count")[:limit]

    def recently_added(self, days=30, limit=30):
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return (
            self.active()
            .filter(created_at__gte=cutoff_date)
            .order_by("-created_at")[:limit]
        )

    def price_range(self, min_price=None, max_price=None):
        queryset = self.active()

        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)

        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)

        return queryset

    # TODO add more functionality to get cache
    def get_cached(self, slug):
        cache_key = f"menuitem:slug:{slug}"
        cached_item = cache.get(cache_key)

        if cached_item is None:
            try:
                item = self.get(slug=slug)
                cache.set(cache_key, item, timeout=3600)
            except self.model.DoesNotExist:
                return None
            else:
                return item

        return cached_item

    def search(self, query):
        return (
            self.get_queryset()
            .filter(
                models.Q(name__icontains=query)
                | models.Q(description__icontains=query)
                | models.Q(body__icontains=query)
            )
            .distinct()
        )
