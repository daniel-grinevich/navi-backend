from decimal import Decimal

import factory

from navi_backend.awards.models import Award
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import Tier
from navi_backend.awards.models import UserLoyalty
from navi_backend.core.tests.factories import AuditFactory
from navi_backend.core.tests.factories import StatusFactory
from navi_backend.core.tests.factories import UpdateRecordFactory
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


class UserLoyaltyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserLoyalty

    user = factory.SubFactory(UserFactory)
    lifetime_points = 0
    balance_points = 0
    orders_completed = 0
    total_spent = Decimal("0.00")
    notifications_enabled = True
