"""Read-side selector for a user's achievement progress.

Builds the payload behind ``GET /api/my/achievements/progress/``: the user's
points and tier, plus one row per active award with the full level ladder so
the frontend can draw progress gauges. Single-threshold awards are presented
as a one-level ladder so every row has the same shape.
"""

from navi_backend.awards.models import Award
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.services.rules import metric_value

# What the metric behind each rule type counts, for labels like "12 / 25 orders".
RULE_UNITS = {
    RuleType.ORDERS_COMPLETED: "orders",
    RuleType.DISTINCT_ITEMS: "drinks",
    RuleType.CUSTOMIZATIONS: "customizations",
    RuleType.TOTAL_POINTS: "points",
    RuleType.TOTAL_SPENT: "dollars",
}

# Default UI grouping when an award has no explicit ``category``.
RULE_CATEGORIES = {
    RuleType.ORDERS_COMPLETED: "habits",
    RuleType.DISTINCT_ITEMS: "exploration",
    RuleType.CUSTOMIZATIONS: "exploration",
    RuleType.TOTAL_POINTS: "loyalty",
    RuleType.TOTAL_SPENT: "loyalty",
}


def achievement_progress(user) -> dict:
    """Return ``{"summary": ..., "results": [...]}`` for ``user``."""
    loyalty = UserLoyalty.for_user(user)
    user_awards = {
        ua.award_id: ua
        for ua in UserAward.objects.filter(user=user)
        .select_related("level")
        .prefetch_related("level_history")
    }
    awards = (
        Award.objects.filter(status=Award.Status.ACTIVE, is_deleted=False)
        .prefetch_related("levels")
        .order_by("rule_type", "name")
    )

    results = []
    for award in awards:
        row = _award_row(award, user_awards.get(award.id), loyalty)
        if row is not None:
            results.append(row)

    return {
        "summary": _summary(loyalty, results),
        "results": results,
    }


def _summary(loyalty, results) -> dict:
    points = loyalty.lifetime_points
    tiers = Tier.objects.filter(status=Tier.Status.ACTIVE, is_deleted=False).order_by(
        "threshold_points",
        "rank",
    )
    current_tier = None
    next_tier = None
    for tier in tiers:
        if tier.threshold_points <= points:
            current_tier = tier
        else:
            next_tier = tier
            break

    return {
        "points": points,
        "tier": _tier_data(current_tier),
        "next_tier": _tier_data(next_tier),
        "badges_earned": sum(1 for row in results if row["level"] > 0),
        "badges_total": len(results),
    }


def _tier_data(tier):
    if tier is None:
        return None
    return {"slug": tier.slug, "name": tier.name, "min_points": tier.threshold_points}


def _award_row(award, user_award, loyalty):
    """One progress row, or ``None`` for a misconfigured (unearnable) award."""
    ladder = _ladder(award, user_award)
    if not ladder:
        return None

    level = sum(1 for step in ladder if step["earned_at"] is not None)
    max_level = len(ladder)
    return {
        "id": award.id,
        "slug": award.slug,
        "name": award.name,
        "description": award.description,
        "category": award.category or RULE_CATEGORIES.get(award.rule_type, ""),
        "icon": award.icon,
        "level": level,
        "max_level": max_level,
        "current_value": int(metric_value(award.rule_type, loyalty)),
        "prev_threshold": ladder[level - 1]["threshold"] if level else 0,
        "next_threshold": ladder[level]["threshold"] if level < max_level else None,
        "unit": RULE_UNITS.get(award.rule_type, ""),
        "earned_at": ladder[level - 1]["earned_at"] if level else None,
        "levels": ladder,
    }


def _ladder(award, user_award) -> list[dict]:
    """Every level of ``award`` with the time the user reached it (or None).

    Levels are earned in order, so the earned ones always form a prefix of the
    ladder. Levels reached before per-level history was recorded fall back to
    the award's first-earned timestamp.
    """
    levels = award.ordered_levels()
    if not levels:
        if not award.threshold:
            return []
        return [
            {
                "level": 1,
                "name": award.name,
                "threshold": award.threshold,
                "earned_at": user_award.earned_at if user_award else None,
            },
        ]

    reached_rank = 0
    history = {}
    if user_award is not None and user_award.level is not None:
        reached_rank = user_award.level.rank
        history = {h.level_id: h.earned_at for h in user_award.level_history.all()}

    return [
        {
            "level": position,
            "name": level.name,
            "threshold": level.threshold,
            "earned_at": (
                history.get(level.id, user_award.earned_at)
                if level.rank <= reached_rank
                else None
            ),
        }
        for position, level in enumerate(levels, start=1)
    ]
