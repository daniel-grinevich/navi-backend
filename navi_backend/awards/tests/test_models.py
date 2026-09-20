from decimal import Decimal

import pytest

from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty

from .factories import AwardFactory
from .factories import TierFactory
from .factories import UserLoyaltyFactory


@pytest.mark.django_db
class TestLoyaltySettings:
    def test_is_singleton(self):
        first = LoyaltySettings.load()
        first.points_per_dollar = Decimal("2.00")
        first.save()

        second = LoyaltySettings.load()
        assert second.pk == 1
        assert second.points_per_dollar == Decimal("2.00")
        assert LoyaltySettings.objects.count() == 1

    def test_save_forces_pk_one(self):
        settings = LoyaltySettings()
        settings.save()
        assert settings.pk == 1


@pytest.mark.django_db
class TestTier:
    def test_slug_auto_generated(self):
        tier = TierFactory(name="Gold Member", slug="")
        assert tier.slug

    def test_str(self):
        tier = TierFactory(name="Gold", threshold_points=2000)
        assert str(tier) == "Gold (2000+ pts)"


@pytest.mark.django_db
class TestAward:
    def test_defaults(self):
        award = AwardFactory(name="Regular", rule_type=RuleType.ORDERS_COMPLETED)
        assert award.threshold == 1
        assert award.points_reward == 0
        assert str(award) == "Regular"


@pytest.mark.django_db
class TestUserLoyalty:
    def test_for_user_is_idempotent(self, user):
        first = UserLoyalty.for_user(user)
        second = UserLoyalty.for_user(user)
        assert first.pk == second.pk
        assert UserLoyalty.objects.filter(user=user).count() == 1

    def test_unique_user_award(self, user):
        award = AwardFactory()
        loyalty = UserLoyaltyFactory(user=user)
        UserAward.objects.create(user=loyalty.user, award=award)
        with pytest.raises(Exception):  # noqa: B017, PT011
            UserAward.objects.create(user=loyalty.user, award=award)
