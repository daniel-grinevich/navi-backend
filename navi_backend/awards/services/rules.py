"""Registry mapping award rule types to the function that computes a user's
current value for that metric.

Adding a new rule type is a two-step change: add a member to
:class:`~navi_backend.awards.models.RuleType` and register a metric function
here with the ``@metric`` decorator. Nothing else needs to change.
"""

from navi_backend.awards.models import RuleType
from navi_backend.orders.models import OrderItem

_METRICS = {}


def metric(rule_type):
    """Register ``fn`` as the metric resolver for ``rule_type``."""

    def decorator(fn):
        _METRICS[rule_type] = fn
        return fn

    return decorator


def metric_value(rule_type, loyalty):
    """Return the current value of ``rule_type`` for the given ``UserLoyalty``.

    Unknown rule types resolve to ``0`` so a misconfigured award can never be
    auto-earned.
    """
    fn = _METRICS.get(rule_type)
    if fn is None:
        return 0
    return fn(loyalty)


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
