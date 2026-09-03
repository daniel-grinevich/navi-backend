import pytest
from rest_framework.test import APIRequestFactory

from navi_backend.awards.api.views import AwardViewSet
from navi_backend.awards.api.views import LoyaltySettingsView
from navi_backend.awards.api.views import MyAwardsViewSet
from navi_backend.awards.api.views import MyLoyaltyView
from navi_backend.awards.api.views import TierViewSet
from navi_backend.awards.models import LoyaltySettings
from navi_backend.awards.models import RuleType
from navi_backend.awards.models import UserAward
from navi_backend.awards.models import UserLoyalty
from navi_backend.users.tests.factories import UserFactory

from .factories import AwardFactory
from .factories import TierFactory


@pytest.fixture
def api_rf():
    return APIRequestFactory()


@pytest.fixture
def staff_user(db):
    return UserFactory(is_staff=True)


@pytest.mark.django_db
class TestTierAPI:
    def test_authenticated_user_can_list_active_tiers(self, user, api_rf):
        TierFactory(name="Bronze", threshold_points=0, status="A")
        TierFactory(name="Hidden", threshold_points=10, status="I")

        view = TierViewSet.as_view({"get": "list"})
        request = api_rf.get("/tiers/")
        request.user = user
        response = view(request)

        assert response.status_code == 200
        names = {t["name"] for t in response.data}
        assert "Bronze" in names
        assert "Hidden" not in names

    def test_non_staff_cannot_create_tier(self, user, api_rf):
        view = TierViewSet.as_view({"post": "create"})
        request = api_rf.post(
            "/tiers/",
            {"name": "Platinum", "threshold_points": 5000},
            format="json",
        )
        request.user = user
        response = view(request)
        assert response.status_code == 403

    def test_staff_can_create_tier(self, staff_user, api_rf):
        view = TierViewSet.as_view({"post": "create"})
        request = api_rf.post(
            "/tiers/",
            {"name": "Platinum", "threshold_points": 5000, "rank": 5},
            format="json",
        )
        request.user = staff_user
        response = view(request)
        assert response.status_code == 201
        assert response.data["name"] == "Platinum"


@pytest.mark.django_db
class TestAwardAPI:
    def test_staff_can_create_award(self, staff_user, api_rf):
        view = AwardViewSet.as_view({"post": "create"})
        request = api_rf.post(
            "/awards/",
            {
                "name": "Explorer",
                "rule_type": RuleType.DISTINCT_ITEMS,
                "threshold": 5,
                "points_reward": 100,
            },
            format="json",
        )
        request.user = staff_user
        response = view(request)
        assert response.status_code == 201
        assert response.data["rule_type"] == RuleType.DISTINCT_ITEMS


@pytest.mark.django_db
class TestMyLoyaltyAPI:
    def test_get_summary_includes_progress(self, user, api_rf):
        AwardFactory(name="Regular", rule_type=RuleType.ORDERS_COMPLETED, threshold=10)

        view = MyLoyaltyView.as_view()
        request = api_rf.get("/my/loyalty/")
        request.user = user
        response = view(request)

        assert response.status_code == 200
        assert response.data["lifetime_points"] == 0
        assert len(response.data["award_progress"]) == 1
        assert response.data["award_progress"][0]["threshold"] == 10

    def test_user_can_toggle_own_notifications(self, user, api_rf):
        view = MyLoyaltyView.as_view()
        request = api_rf.patch(
            "/my/loyalty/",
            {"notifications_enabled": False},
            format="json",
        )
        request.user = user
        response = view(request)

        assert response.status_code == 200
        assert response.data["notifications_enabled"] is False
        assert UserLoyalty.for_user(user).notifications_enabled is False


@pytest.mark.django_db
class TestLoyaltySettingsAPI:
    def test_non_staff_forbidden(self, user, api_rf):
        view = LoyaltySettingsView.as_view()
        request = api_rf.get("/loyalty-settings/")
        request.user = user
        response = view(request)
        assert response.status_code == 403

    def test_staff_can_toggle_global_notifications(self, staff_user, api_rf):
        view = LoyaltySettingsView.as_view()
        request = api_rf.patch(
            "/loyalty-settings/",
            {"notifications_enabled": False},
            format="json",
        )
        request.user = staff_user
        response = view(request)

        assert response.status_code == 200
        assert response.data["notifications_enabled"] is False
        assert LoyaltySettings.load().notifications_enabled is False


@pytest.mark.django_db
class TestMyAwardsAPI:
    def test_lists_only_own_awards(self, user, api_rf):
        award = AwardFactory()
        other_user = UserFactory()
        UserAward.objects.create(user=user, award=award)
        UserAward.objects.create(user=other_user, award=award)

        view = MyAwardsViewSet.as_view({"get": "list"})
        request = api_rf.get("/my/awards/")
        request.user = user
        response = view(request)

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["award"]["id"] == str(award.id)
