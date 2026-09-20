"""Stampede-safe caching helpers.

The naive ``get -> miss -> compute -> set`` pattern lets every request that
sees the same miss recompute the value simultaneously (a cache stampede).
:func:`get_or_set_safe` serializes recomputation behind a short-lived lock
(atomic ``cache.add``, so it works on Redis and LocMem alike) and serves
slightly-stale data to everyone else while a single caller refreshes.

Invalidation is done with namespace version keys (:func:`versioned_key` /
:func:`bump_version`): bumping the version orphans every key built under the
old one, which beats trying to enumerate and delete individual keys.
"""

import time

from django.core.cache import cache

# Sentinel distinguishing "cached None" from a cache miss.
_MISS = object()


def get_or_set_safe(  # noqa: PLR0913
    key,
    producer,
    ttl,
    *,
    stale_grace=60,
    lock_timeout=30,
    wait_interval=0.05,
    wait_attempts=40,
):
    """Return the cached value for ``key``, computing it at most once at a time.

    ``ttl`` is the freshness window; after it lapses the value is served stale
    for up to ``stale_grace`` seconds while ONE caller (the lock winner)
    re-runs ``producer``. On a cold miss, lock losers briefly poll for the
    winner's result and only fall back to computing (without writing) if the
    winner takes longer than ``wait_interval * wait_attempts`` seconds.

    If ``producer`` raises, nothing is cached and the error propagates.
    """
    entry = cache.get(key, _MISS)
    now = time.time()
    if entry is not _MISS and now < entry["fresh_until"]:
        return entry["value"]

    lock_key = f"{key}:lock"
    won_lock = cache.add(lock_key, 1, lock_timeout)

    if entry is not _MISS:
        # Stale-but-present: losers serve stale, the winner refreshes.
        if not won_lock:
            return entry["value"]
        try:
            return _refresh(key, producer, ttl, stale_grace)
        finally:
            cache.delete(lock_key)

    if won_lock:
        try:
            return _refresh(key, producer, ttl, stale_grace)
        finally:
            cache.delete(lock_key)

    # Cold miss and someone else is computing: wait briefly for their result.
    for _ in range(wait_attempts):
        time.sleep(wait_interval)
        entry = cache.get(key, _MISS)
        if entry is not _MISS:
            return entry["value"]
    # Winner is slow or died; compute for this caller only. Skip the write so
    # a stale straggler can't clobber a fresher value written by the winner.
    return producer()


def _refresh(key, producer, ttl, stale_grace):
    value = producer()
    cache.set(
        key,
        {"value": value, "fresh_until": time.time() + ttl},
        ttl + stale_grace,
    )
    return value


def versioned_key(namespace, suffix):
    """Build a cache key under ``namespace``'s current version."""
    return f"{namespace}:v{_current_version(namespace)}:{suffix}"


def bump_version(namespace):
    """Invalidate every key built with :func:`versioned_key` for ``namespace``."""
    version_key = f"cachever:{namespace}"
    try:
        cache.incr(version_key)
    except ValueError:
        # Version key evicted or never existed. A timestamp can't collide with
        # any version baked into live keys, so those keys are all orphaned.
        cache.set(version_key, int(time.time()), None)


def _current_version(namespace):
    version = cache.get(f"cachever:{namespace}")
    if version is None:
        cache.add(f"cachever:{namespace}", 1, None)
        version = cache.get(f"cachever:{namespace}") or 1
    return version
