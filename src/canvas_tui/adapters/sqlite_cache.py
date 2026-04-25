"""
SQLite cache adapter for the TUI.

Implements CacheBackend from core.interfaces using SQLite.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.interfaces import CacheBackend


class SQLiteCache(CacheBackend):
    """SQLite-backed cache with TTL and optional offline fallback."""

    def __init__(self, db_path: str | Path = "~/.cache/canvas-tui/cache.db"):
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")
        self._conn.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?",
            (key,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] and row["expires_at"] < time.time():
            self.invalidate(key)
            return None
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), expires_at)
        )
        self._conn.commit()

    def invalidate(self, key: str) -> None:
        self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()