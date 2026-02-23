"""Disk-backed response cache with TTL for offline mode."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from typing import Any


class ResponseCache:
    """Cache Canvas API responses to disk with configurable TTL.

    Supports:
    - TTL-based expiry (default 15 min)
    - Stale-while-offline: returns expired cache on network failure
    - Thread-safe (file-level atomicity via rename)
    """

    def __init__(self, cache_dir: str, default_ttl: int = 900) -> None:
        self._dir = cache_dir
        self._ttl = default_ttl
        os.makedirs(self._dir, exist_ok=True)

    def _key_path(self, key: str) -> str:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self._dir, f"{h}.json")

    def get(self, key: str, allow_stale: bool = False) -> tuple[Any | None, bool]:
        """Get cached value.

        Returns:
            (value, is_stale) — value is None if no cache exists.
            is_stale is True if the entry has expired but allow_stale=True.
        """
        path = self._key_path(key)
        if not os.path.exists(path):
            return None, False
        try:
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
            ts = entry.get("ts", 0)
            age = time.time() - ts
            if age <= self._ttl:
                return entry.get("data"), False
            if allow_stale:
                return entry.get("data"), True
            return None, False
        except Exception:
            return None, False

    def put(self, key: str, data: Any) -> None:
        """Store data in cache with current timestamp."""
        path = self._key_path(key)
        tmp = path + ".tmp"
        entry = {"ts": time.time(), "data": data}
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(entry, f)
            os.replace(tmp, path)
        except Exception:
            with contextlib.suppress(Exception):
                os.remove(tmp)

    def invalidate(self, key: str) -> None:
        """Remove a cache entry."""
        path = self._key_path(key)
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)

    def clear(self) -> None:
        """Clear all cache entries."""
        try:
            for f in os.listdir(self._dir):
                if f.endswith(".json"):
                    os.remove(os.path.join(self._dir, f))
        except Exception:
            pass

    def stats(self) -> dict[str, Any]:
        """Return cache stats."""
        total = 0
        expired = 0
        size_bytes = 0
        now = time.time()
        try:
            for f in os.listdir(self._dir):
                if not f.endswith(".json"):
                    continue
                total += 1
                path = os.path.join(self._dir, f)
                size_bytes += os.path.getsize(path)
                try:
                    with open(path, encoding="utf-8") as fh:
                        entry = json.load(fh)
                    if now - entry.get("ts", 0) > self._ttl:
                        expired += 1
                except Exception:
                    expired += 1
        except Exception:
            pass
        return {
            "entries": total,
            "expired": expired,
            "size_kb": round(size_bytes / 1024, 1),
        }


def cache_key(endpoint: str, params: dict[str, Any] | None = None) -> str:
    """Build a cache key from endpoint + params."""
    parts = [endpoint]
    if params:
        for k in sorted(params.keys()):
            v = params[k]
            if isinstance(v, list):
                v = ",".join(str(x) for x in v)
            parts.append(f"{k}={v}")
    return "|".join(parts)
