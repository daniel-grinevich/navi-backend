"""Registry mapping award rule types to the function that computes a user's
current value for that metric.

Adding a new rule type is a two-step change: add a member to
:class:`~navi_backend.awards.models.RuleType` and register a metric function
here with the ``@metric`` decorator. Nothing else needs to change.
"""

from django.core.cache import cache

from navi_backend.awards.models import RuleType
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem

_METRICS = {}

# These metrics are computed with an aggregate query over a user's order history
# (unlike the others, which just read a denormalized counter off ``loyalty``).
# They are recomputed on every loyalty dashboard / achievements request, so we
# cache them per user and invalidate when the user completes an order
# (see ``invalidate_user_metrics``, called from points_service.process_order).
_CACHED_RULE_TYPES = frozenset({RuleType.DISTINCT_ITEMS, RuleType.CUSTOMIZATIONS})
_METRIC_CACHE_TTL = 60 * 5  # 5 minutes


def metric(rule_type):
    """Register ``fn`` as the metric resolver for ``rule_type``."""

    def decorator(fn):
        _METRICS[rule_type] = fn
        return fn

    return decorator


def _metric_cache_key(user_id, rule_type):
    return f"awards:metric:{user_id}:{rule_type}"


def invalidate_user_metrics(user_id):
    """Drop a user's cached DB-derived metric values (call after their order
    history changes)."""
    cache.delete_many(
        [_metric_cache_key(user_id, rule_type) for rule_type in _CACHED_RULE_TYPES],
    )


def metric_value(rule_type, loyalty):
    """Return the current value of ``rule_type`` for the given ``UserLoyalty``.

    Unknown rule types resolve to ``0`` so a misconfigured award can never be
    auto-earned. Aggregate metrics are served from a short-lived per-user cache.
    """
    fn = _METRICS.get(rule_type)
    if fn is None:
        return 0

    if rule_type not in _CACHED_RULE_TYPES:
        return fn(loyalty)

    key = _metric_cache_key(loyalty.user_id, rule_type)
    cached = cache.get(key)
    if cached is not None:
        return cached
    value = fn(loyalty)
    cache.set(key, value, _METRIC_CACHE_TTL)
    return value


@metric(RuleType.TOTAL_POINTS)
def _total_points(loyalty):
    return loyalty.lifetime_points


@metric(RuleType.ORDERS_COMPLETED)
def _orders_completed(loyalty):
    return loyalty.orders_completed


@metric(RuleType.TOTAL_SPENT)
def _total_spent(loyalty):
    return loyalty.total_spent


@metric(RuleType.DISTINCT_ITEMS)
def _distinct_items(loyalty):
    return (
        OrderItem.objects.filter(
            order__user=loyalty.user,
            order__order_status="D",
        )
        .values("menu_item")
        .distinct()
        .count()
    )


@metric(RuleType.CUSTOMIZATIONS)
def _customizations(loyalty):
    return OrderCustomization.objects.filter(
        order_item__order__user=loyalty.user,
        order_item__order__order_status="D",
    ).count()
