"""Tests for canvas_tui.cache module."""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from canvas_tui.cache import ResponseCache, cache_key


class TestResponseCache:
    """Unit tests for ResponseCache disk cache."""

    def setup_method(self) -> None:
        """Create a clean temp cache directory before each test."""
        self.cache_dir = tempfile.mkdtemp(prefix="cache_test_")
        self.cache = ResponseCache(self.cache_dir, default_ttl=60)

    def teardown_method(self) -> None:
        """Remove temp cache directory after each test."""
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_put_and_get(self) -> None:
        """Basic put then get returns the data."""
        self.cache.put("test-key", {"value": 42})
        result, is_stale = self.cache.get("test-key")
        assert result == {"value": 42}
        assert is_stale is False

    def test_miss_returns_none(self) -> None:
        """Get on a missing key returns None, not stale."""
        result, is_stale = self.cache.get("nonexistent-key")
        assert result is None
        assert is_stale is False

    def test_expired_not_returned_without_stale(self) -> None:
        """Expired entries return None when allow_stale=False."""
        self.cache.put("expired-key", {"data": "old"})
        # Manually backdate the cache entry
        path = self.cache._key_path("expired-key")
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
        entry["ts"] = entry["ts"] - 120  # 2 minutes ago, TTL is 60s
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f)

        result, _is_stale = self.cache.get("expired-key", allow_stale=False)
        assert result is None

    def test_stale_returned_when_allowed(self) -> None:
        """Expired entries are returned as stale when allow_stale=True."""
        self.cache.put("stale-key", {"data": "stale-value"})
        # Manually backdate the cache entry
        path = self.cache._key_path("stale-key")
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
        entry["ts"] = entry["ts"] - 120
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f)

        result, is_stale = self.cache.get("stale-key", allow_stale=True)
        assert result == {"data": "stale-value"}
        assert is_stale is True

    def test_invalidate(self) -> None:
        """Invalidate removes the entry and subsequent get returns None."""
        self.cache.put("invalidate-key", {"data": "value"})
        assert self.cache.get("invalidate-key")[0] is not None

        self.cache.invalidate("invalidate-key")
        result, _ = self.cache.get("invalidate-key")
        assert result is None

    def test_clear(self) -> None:
        """Clear removes all entries from the cache directory."""
        self.cache.put("key1", "value1")
        self.cache.put("key2", "value2")
        self.cache.put("key3", "value3")
        assert len(os.listdir(self.cache_dir)) >= 3

        self.cache.clear()
        entries = [f for f in os.listdir(self.cache_dir) if f.endswith(".json")]
        assert len(entries) == 0

    def test_stats(self) -> None:
        """Stats returns correct counts and size."""
        self.cache.put("key1", "value1")
        self.cache.put("key2", "value2")
        stats = self.cache.stats()
        assert stats["entries"] == 2
        assert stats["expired"] == 0
        assert stats["size_kb"] > 0

    def test_purge_expired(self) -> None:
        """Purge removes entries older than max_age_sec, keeps fresh ones."""
        self.cache.put("fresh-key", {"data": "fresh"})
        self.cache.put("old-key", {"data": "old"})

        # Backdate the "old" entry
        old_path = self.cache._key_path("old-key")
        with open(old_path, encoding="utf-8") as f:
            entry = json.load(f)
        entry["ts"] = entry["ts"] - 86400  # 1 day ago
        with open(old_path, "w", encoding="utf-8") as f:
            json.dump(entry, f)

        removed = self.cache.purge_expired(max_age_sec=3600)  # 1 hour
        assert removed == 1

        # Fresh key still there
        assert self.cache.get("fresh-key")[0] is not None
        # Old key gone
        assert self.cache.get("old-key")[0] is None

    def test_purge_keeps_fresh(self) -> None:
        """Entries within max_age_sec are never removed by purge."""
        self.cache.put("keep-key", {"data": "keep"})
        removed = self.cache.purge_expired(max_age_sec=86400)
        assert removed == 0
        assert self.cache.get("keep-key")[0] is not None


class TestCacheKey:
    """Unit tests for the cache_key helper function."""

    def test_basic(self) -> None:
        """Basic endpoint and params produce a string key."""
        key = cache_key("/api/courses")
        assert isinstance(key, str)
        assert "/api/courses" in key

    def test_deterministic(self) -> None:
        """Same inputs always produce the same key."""
        params = {"type": "assignment", "per_page": 50}
        key1 = cache_key("/api/courses", params)
        key2 = cache_key("/api/courses", params)
        assert key1 == key2

    def test_no_params(self) -> None:
        """Endpoint with no params produces a stable key."""
        key = cache_key("/api/users/me")
        assert key is not None
        assert isinstance(key, str)
        # Calling twice with same inputs gives same key
        assert cache_key("/api/users/me") == key

    def test_params_order_sorted(self) -> None:
        """Params are sorted so order doesn't affect key."""
        params_a = {"a": 1, "b": 2}
        params_b = {"b": 2, "a": 1}
        assert cache_key("/api/test", params_a) == cache_key("/api/test", params_b)

    def test_list_values(self) -> None:
        """List params are flattened into the key."""
        params = {"courses": [101, 102, 103]}
        key = cache_key("/api/courses", params)
        assert "101" in key
        assert "102" in key
        assert "103" in key
