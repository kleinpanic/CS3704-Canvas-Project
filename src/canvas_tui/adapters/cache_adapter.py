"""
ResponseCache adapter — wraps ResponseCache to implement CacheBackend.

ResponseCache uses (get → tuple[value, is_stale], put → (key, data)) while
CacheBackend uses (get → value|None, set → (key, value, ttl)).  This adapter
bridges the two APIs so ResponseCache can be used wherever a CacheBackend is
expected (e.g. in commands/registry.py).
"""

from __future__ import annotations

from typing import Any

from ..cache import ResponseCache
from ..core.interfaces import CacheBackend


class CacheBackendAdapter(CacheBackend):
    """Wraps ResponseCache to satisfy the CacheBackend interface."""

    def __init__(self, response_cache: ResponseCache) -> None:
        self._cache = response_cache

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve cached response. Returns None on miss or expired."""
        value, _ = self._cache.get(key, allow_stale=False)
        return value

    def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        """Store a response under key."""
        # ResponseCache has no per-entry TTL; use default_ttl at construction time.
        self._cache.put(key, value)

    def invalidate(self, key: str) -> None:
        """Remove a key from the cache."""
        self._cache.invalidate(key)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
