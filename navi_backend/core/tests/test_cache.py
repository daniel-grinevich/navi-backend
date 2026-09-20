"""Tests for the stampede-safe cache helpers."""

import time
from unittest import mock

import pytest
from django.core.cache import cache

from navi_backend.core.cache import bump_version
from navi_backend.core.cache import get_or_set_safe
from navi_backend.core.cache import versioned_key


# The DummyCache used by the test settings never stores anything, so these
# tests run against a real in-process cache.
@pytest.fixture(autouse=True)
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    }
    cache.clear()
    yield
    cache.clear()


class TestGetOrSetSafe:
    def test_computes_once_then_serves_cached(self):
        producer = mock.Mock(return_value="payload")

        assert get_or_set_safe("k", producer, ttl=60) == "payload"
        assert get_or_set_safe("k", producer, ttl=60) == "payload"
        assert producer.call_count == 1

    def test_caches_none_values(self):
        producer = mock.Mock(return_value=None)

        assert get_or_set_safe("k", producer, ttl=60) is None
        assert get_or_set_safe("k", producer, ttl=60) is None
        assert producer.call_count == 1

    def test_stale_entry_served_while_other_caller_refreshes(self):
        get_or_set_safe("k", lambda: "old", ttl=60)
        # Age the entry past its freshness window.
        entry = cache.get("k")
        entry["fresh_until"] = time.time() - 1
        cache.set("k", entry, 60)
        # Someone else holds the refresh lock.
        cache.set("k:lock", 1, 30)

        producer = mock.Mock(return_value="new")
        assert get_or_set_safe("k", producer, ttl=60) == "old"
        producer.assert_not_called()

    def test_stale_entry_refreshed_by_lock_winner(self):
        get_or_set_safe("k", lambda: "old", ttl=60)
        entry = cache.get("k")
        entry["fresh_until"] = time.time() - 1
        cache.set("k", entry, 60)

        assert get_or_set_safe("k", lambda: "new", ttl=60) == "new"
        # Lock released and fresh value stored.
        assert cache.get("k:lock") is None
        assert get_or_set_safe("k", mock.Mock(), ttl=60) == "new"

    def test_cold_miss_lock_loser_waits_for_winners_value(self):
        cache.set("k:lock", 1, 30)

        def winner_writes(_seconds):
            cache.set("k", {"value": "winner", "fresh_until": time.time() + 60}, 60)

        producer = mock.Mock(return_value="loser")
        with mock.patch("navi_backend.core.cache.time.sleep", winner_writes):
            assert get_or_set_safe("k", producer, ttl=60) == "winner"
        producer.assert_not_called()

    def test_cold_miss_lock_loser_falls_back_to_computing(self):
        cache.set("k:lock", 1, 30)

        with mock.patch("navi_backend.core.cache.time.sleep"):
            result = get_or_set_safe("k", lambda: "fallback", ttl=60, wait_attempts=2)

        assert result == "fallback"
        # The fallback path must not write: the winner's eventual value wins.
        assert cache.get("k") is None

    def test_producer_error_caches_nothing_and_releases_lock(self):
        with pytest.raises(RuntimeError):
            get_or_set_safe("k", mock.Mock(side_effect=RuntimeError), ttl=60)
        assert cache.get("k") is None
        assert cache.get("k:lock") is None


class TestVersionedKeys:
    def test_key_stable_until_bumped(self):
        assert versioned_key("menu", "list") == versioned_key("menu", "list")

    def test_bump_changes_keys_for_namespace_only(self):
        menu_before = versioned_key("menu", "list")
        other_before = versioned_key("other", "list")

        bump_version("menu")

        assert versioned_key("menu", "list") != menu_before
        assert versioned_key("other", "list") == other_before

    def test_bump_after_version_eviction_still_invalidates(self):
        before = versioned_key("menu", "list")
        cache.delete("cachever:menu")

        bump_version("menu")

        assert versioned_key("menu", "list") != before
