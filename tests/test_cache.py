"""Tests for response cache."""

from __future__ import annotations

import time

from canvas_tui.cache import ResponseCache, cache_key


class TestResponseCache:
    def test_put_and_get(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=60)
        cache.put("test_key", {"items": [1, 2, 3]})
        data, stale = cache.get("test_key")
        assert data == {"items": [1, 2, 3]}
        assert stale is False

    def test_miss_returns_none(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=60)
        data, stale = cache.get("nonexistent")
        assert data is None
        assert stale is False

    def test_expired_not_returned_without_stale(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=0)  # Immediate expiry
        cache.put("test_key", {"x": 1})
        time.sleep(0.1)
        data, _stale = cache.get("test_key", allow_stale=False)
        assert data is None

    def test_stale_returned_when_allowed(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=0)
        cache.put("test_key", {"x": 1})
        time.sleep(0.1)
        data, stale = cache.get("test_key", allow_stale=True)
        assert data == {"x": 1}
        assert stale is True

    def test_invalidate(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=60)
        cache.put("test_key", "data")
        cache.invalidate("test_key")
        data, _ = cache.get("test_key")
        assert data is None

    def test_clear(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=60)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.clear()
        d1, _ = cache.get("k1")
        d2, _ = cache.get("k2")
        assert d1 is None
        assert d2 is None

    def test_stats(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=60)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        stats = cache.stats()
        assert stats["entries"] == 2
        assert stats["size_kb"] > 0

    def test_purge_expired(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=0)
        cache.put("old1", "data1")
        cache.put("old2", "data2")
        import time

        time.sleep(0.1)
        removed = cache.purge_expired(max_age_sec=0)
        assert removed == 2
        assert cache.stats()["entries"] == 0

    def test_purge_keeps_fresh(self, tmp_dir):
        cache = ResponseCache(tmp_dir, default_ttl=3600)
        cache.put("fresh", "data")
        removed = cache.purge_expired(max_age_sec=3600)
        assert removed == 0
        assert cache.stats()["entries"] == 1


class TestCacheKey:
    def test_basic(self):
        k = cache_key("/api/v1/courses", {"per_page": 100})
        assert "/api/v1/courses" in k
        assert "per_page=100" in k

    def test_deterministic(self):
        k1 = cache_key("/api/v1/courses", {"a": 1, "b": 2})
        k2 = cache_key("/api/v1/courses", {"b": 2, "a": 1})
        assert k1 == k2  # Sorted keys

    def test_no_params(self):
        k = cache_key("/api/v1/users/self")
        assert k == "/api/v1/users/self"
