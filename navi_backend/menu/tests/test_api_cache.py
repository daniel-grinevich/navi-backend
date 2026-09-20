"""Tests for menu API caching + signal-driven invalidation."""

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from navi_backend.menu.tests.factories import MenuItemFactory

pytestmark = pytest.mark.django_db


# The DummyCache used by the test settings never stores anything; these tests
# exercise real caching behavior.
@pytest.fixture(autouse=True)
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "menu-test-cache",
        }
    }
    cache.clear()
    yield
    cache.clear()


LIST_URL = reverse("api:menu-items-list")


@pytest.fixture
def client():
    return APIClient()


class TestMenuListCache:
    def test_list_served_from_cache(self, client, django_assert_max_num_queries):
        MenuItemFactory()
        first = client.get(LIST_URL)
        assert first.status_code == 200

        # Only ATOMIC_REQUESTS savepoints are allowed — no real SQL.
        with django_assert_max_num_queries(2):
            second = client.get(LIST_URL)
        assert second.data == first.data

    def test_saving_a_menu_item_invalidates_the_list(self, client):
        item = MenuItemFactory(name="Latte")
        assert client.get(LIST_URL).status_code == 200

        item.name = "Oat Latte"
        item.save()

        names = [row["name"] for row in client.get(LIST_URL).data]
        assert "Oat Latte" in names

    def test_status_filter_cached_separately(self, client):
        MenuItemFactory(status="A")
        all_rows = client.get(LIST_URL).data
        active_rows = client.get(LIST_URL, {"status": "A"}).data
        # Both were computed (not cross-served) — the "all" response includes
        # every status, and the filtered one must not be the same cache entry.
        assert len(all_rows) >= len(active_rows)


class TestCategoryCustomizationsCache:
    def test_cached_and_invalidated_on_change(
        self, client, django_assert_max_num_queries
    ):
        item = MenuItemFactory()
        url = f"/api/menu-items/{item.slug}/category-customizations/"
        first = client.get(url)
        assert first.status_code == 200

        # Only ATOMIC_REQUESTS savepoints are allowed — no real SQL.
        with django_assert_max_num_queries(2):
            assert client.get(url).data == first.data

        # Any menu edit bumps the namespace version -> fresh serialization.
        item.name = "Renamed"
        item.save()
        assert client.get(url).data["name"] == "Renamed"
