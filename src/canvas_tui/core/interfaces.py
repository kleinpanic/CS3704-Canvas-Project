"""
Core domain interfaces for Canvas Deadline Tracker.

These abstract the Canvas client, caching, and auth so the TUI and browser
extension can share the same business logic with different adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ── Cache ──────────────────────────────────────────────────────────────────────

class CacheBackend(ABC):
    """Abstract cache. Implement with SQLite for TUI, IndexedDB for extension."""

    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve cached response by key. Returns None on miss or expired."""
        ...

    @abstractmethod
    def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        """Store a response under key. Optionally expire after ttl seconds."""
        ...

    @abstractmethod
    def invalidate(self, key: str) -> None:
        """Remove a key from the cache."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached entries."""
        ...


# ── Auth ──────────────────────────────────────────────────────────────────────

@dataclass
class TokenInfo:
    """Validated token with metadata."""
    token: str
    user_id: int
    user_name: str
    base_url: str
    valid_until: datetime | None = None


class AuthManager(ABC):
    """Abstract auth. Token storage is platform-specific (keyring vs chrome.storage)."""

    @abstractmethod
    def load_token(self) -> TokenInfo | None:
        """Load the stored token. Returns None if not present or expired."""
        ...

    @abstractmethod
    def save_token(self, token: TokenInfo) -> None:
        """Persist the token."""
        ...

    @abstractmethod
    def clear_token(self) -> None:
        """Remove the stored token."""
        ...


# ── Canvas Client ──────────────────────────────────────────────────────────────

@dataclass
class Course:
    id: int
    name: str
    course_code: str
    account_id: int | None = None
    enrollment_term_id: int | None = None
    grade_passback_ips: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    enrollments: list[dict[str, Any]] = field(default_factory=list)
    teachers: list[dict[str, Any]] = field(default_factory=list)
    total_students: int | None = None
    hide_final_grades: bool = False
    hw_weight: float | None = None
    hw_drop_lowest: int | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Course:
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            course_code=data.get("course_code", ""),
            account_id=data.get("account_id"),
            enrollment_term_id=data.get("enrollment_term_id"),
            grade_passback_ips=data.get("grade_passback_ips"),
            start_at=datetime.fromisoformat(data["start_at"].replace("Z", "+00:00")) if data.get("start_at") else None,
            end_at=datetime.fromisoformat(data["end_at"].replace("Z", "+00:00")) if data.get("end_at") else None,
            enrollments=data.get("enrollments", []),
            teachers=data.get("teachers", []),
            total_students=data.get("total_students"),
            hide_final_grades=data.get("hide_final_grades", False),
            hw_weight=data.get("hw_weight"),
            hw_drop_lowest=data.get("hw_drop_lowest"),
        )


@dataclass
class Assignment:
    id: int
    name: str
    due_at: datetime | None
    points_possible: float
    course_id: int
    submission_types: list[str]
    cached_override: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Assignment:
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            due_at=datetime.fromisoformat(data["due_at"].replace("Z", "+00:00")) if data.get("due_at") else None,
            points_possible=float(data.get("points_possible", 0)),
            course_id=data["course_id"],
            submission_types=data.get("submission_types", []),
            cached_override=data.get("cached_override", False),
        )


@dataclass
class Submission:
    assignment_id: int
    user_id: int
    score: float | None
    submitted_at: datetime | None
    state: str  # "submitted", "graded", "late", etc.


class CanvasClient(ABC):
    """Abstract Canvas API client. Shares business logic across TUI and extension."""

    @abstractmethod
    def validate_token(self) -> bool:
        ...

    @abstractmethod
    def fetch_courses(self) -> list[Course]:
        ...

    @abstractmethod
    def fetch_assignments(self, course_id: int) -> list[Assignment]:
        ...

    @abstractmethod
    def fetch_grades(self, course_id: int) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def fetch_announcements(self, course_ids: list[int], since: datetime) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def fetch_upcoming(self) -> list[dict[str, Any]]:
        """Fetch upcoming assignments across all enrolled courses."""
        ...

    @abstractmethod
    def fetch_course_info(self, course_id: int) -> dict[str, Any] | None:
        ...