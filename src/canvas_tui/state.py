"""Thread-safe state manager for Canvas TUI."""

from __future__ import annotations

import json
import os
import threading
from typing import Any


class StateManager:
    """Thread-safe state store backed by a JSON file.

    All reads/writes go through a lock to prevent race conditions
    from concurrent threads (auto-refresh, pomodoro, UI).
    """

    def __init__(self, state_path: str) -> None:
        self._path = state_path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._load()
        self._ensure_defaults()

    def _load(self) -> dict[str, Any]:
        """Load state from disk."""
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _ensure_defaults(self) -> None:
        """Ensure required keys exist."""
        self._data.setdefault("visibility", {})
        self._data.setdefault("priority", {})
        self._data.setdefault("bucket", {})
        self._data.setdefault("pomo_end_ts", None)
        self._data.setdefault("cache_items", [])
        self._data.setdefault("cache_announcements", [])
        self._data.setdefault("notes", {})
        self._data.setdefault("last_filters", {})

    def save(self) -> None:
        """Atomic save to disk (thread-safe)."""
        with self._lock:
            self._save_unsafe()

    def _save_unsafe(self) -> None:
        """Save without acquiring the lock (caller must hold it)."""
        tmp = self._path + ".tmp"
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self._path)

    def get(self, key: str, default: Any = None) -> Any:
        """Thread-safe get."""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Thread-safe set + persist."""
        with self._lock:
            self._data[key] = value
            self._save_unsafe()

    def get_visibility(self, item_key: str) -> int:
        """Get visibility for an item (0=visible, 1=dimmed, 2=hidden)."""
        with self._lock:
            return self._data["visibility"].get(item_key, 0)

    def set_visibility(self, item_key: str, value: int) -> None:
        """Set visibility for an item and persist."""
        with self._lock:
            self._data["visibility"][item_key] = value
            self._save_unsafe()

    def cycle_visibility(self, item_key: str) -> int:
        """Cycle visibility: 0 -> 1 -> 2 -> 0."""
        with self._lock:
            current = self._data["visibility"].get(item_key, 0)
            new_val = (current + 1) % 3
            self._data["visibility"][item_key] = new_val
            self._save_unsafe()
            return new_val

    def get_pomo_end(self) -> float | None:
        """Get pomodoro end timestamp."""
        with self._lock:
            val = self._data.get("pomo_end_ts")
            return float(val) if val is not None else None

    def set_pomo_end(self, ts: float | None) -> None:
        """Set pomodoro end timestamp."""
        with self._lock:
            self._data["pomo_end_ts"] = ts
            self._save_unsafe()

    def update_cache(self, items: list[dict[str, Any]], announcements: list[dict[str, Any]]) -> None:
        """Update item and announcement caches."""
        with self._lock:
            self._data["cache_items"] = items
            self._data["cache_announcements"] = announcements
            self._save_unsafe()

    def get_cached_items(self) -> list[dict[str, Any]]:
        """Get cached planner items."""
        with self._lock:
            return list(self._data.get("cache_items") or [])

    def get_cached_announcements(self) -> list[dict[str, Any]]:
        """Get cached announcements."""
        with self._lock:
            return list(self._data.get("cache_announcements") or [])

    def migrate_visibility_keys(self, key_map: dict[str, str]) -> int:
        """Migrate legacy visibility keys to stable keys.

        Args:
            key_map: Dict of {legacy_key: stable_key}

        Returns:
            Number of keys migrated.
        """
        with self._lock:
            vis = self._data.get("visibility", {})
            moved = 0
            for legacy, stable in key_map.items():
                if legacy in vis and stable not in vis:
                    vis[stable] = vis[legacy]
                    del vis[legacy]
                    moved += 1
            if moved:
                self._data["visibility"] = vis
                self._save_unsafe()
            return moved

    def get_note(self, item_key: str) -> str:
        """Get note for an item."""
        with self._lock:
            return self._data.get("notes", {}).get(item_key, "")

    def set_note(self, item_key: str, text: str) -> None:
        """Set note for an item."""
        with self._lock:
            self._data.setdefault("notes", {})[item_key] = text
            self._save_unsafe()

    @property
    def raw(self) -> dict[str, Any]:
        """Direct access to underlying data (for backward compat). Use sparingly."""
        return self._data
