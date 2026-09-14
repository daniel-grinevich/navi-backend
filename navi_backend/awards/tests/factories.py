from decimal import Decimal

import factory

from navi_backend.awards.models import Award
from navi_backend.awards.models import AwardLevel
from navi_backend.awards.models import Promotion
from navi_backend.awards.models import PromotionEffect
from navi_backend.awards.models import PromotionScope
from navi_backend.awards.models import Reward
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserLoyalty
from navi_backend.core.tests.factories import AuditFactory
from navi_backend.core.tests.factories import StatusFactory
from navi_backend.core.tests.factories import UpdateRecordFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.users.tests.factories import UserFactory


class TierFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Tier

    name = factory.Sequence(lambda n: f"Tier {n:03d}")
    slug = factory.Sequence(lambda n: f"tier-{n:04d}")
    threshold_points = 0
    rank = factory.Sequence(lambda n: n)
    status = "A"


class AwardFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Award

    name = factory.Sequence(lambda n: f"Award {n:03d}")
    slug = factory.Sequence(lambda n: f"award-{n:04d}")
    rule_type = RuleType.ORDERS_COMPLETED
    threshold = 1
    points_reward = 0
    status = "A"


class AwardLevelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AwardLevel

    award = factory.SubFactory(AwardFactory, threshold=None)
    rank = factory.Sequence(lambda n: n + 1)
    name = factory.Sequence(lambda n: f"Level {n + 1}")
    threshold = 1
    points_reward = 0


class UserLoyaltyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserLoyalty

    user = factory.SubFactory(UserFactory)
    lifetime_points = 0
    balance_points = 0
    orders_completed = 0
    total_spent = Decimal("0.00")
    notifications_enabled = True


class RewardFactory(
    AuditFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    """A live free-item reward on a specific menu item.

    Targets are exclusive: pass ``menu_item=None`` alongside ``category=`` or
    ``customization=``.
    """

    class Meta:
        model = Reward

    name = factory.Sequence(lambda n: f"Reward {n:04d}")
    slug = factory.Sequence(lambda n: f"reward-{n:04d}")
    status = "A"
    points_cost = 200
    max_value = Decimal("6.00")
    menu_item = factory.SubFactory(MenuItemFactory)


class PromotionFactory(
    AuditFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    """A live, always-on, order-wide double-points promotion."""

    class Meta:
        model = Promotion

    name = factory.Sequence(lambda n: f"Promotion {n:04d}")
    slug = factory.Sequence(lambda n: f"promotion-{n:04d}")
    status = "A"
    scope = PromotionScope.ORDER
    effect = PromotionEffect.MULTIPLIER
    multiplier = Decimal("2.00")
    bonus_points = None
