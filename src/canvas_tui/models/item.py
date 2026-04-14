"""CanvasItem — normalized planner/announcement item."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CanvasItem:
    """A normalized planner/announcement item.

    Attributes:
        key: Unique stable identifier (plannable_id or generated).
        ptype: Item type — assignment, quiz, discussion, exam, event, announcement.
        title: Display name.
        course_code: Short code e.g. "CS 3704".
        course_name: Full course name.
        due_at: Human-readable due date string.
        due_rel: Relative time string e.g. "in 2 days".
        due_iso: ISO8601 datetime string for sorting.
        url: Link to the item in Canvas.
        course_id: Numeric Canvas course ID.
        plannable_id: Canvas plannable ID.
        points: Max points.
        status_flags: List of flags — "submitted", " excused", "missing", etc.
        raw_plannable: Original API dict for debugging.
    """

    key: str = ""
    legacy_key: str = ""
    ptype: str = ""
    title: str = "(untitled)"
    course_code: str = ""
    course_name: str = ""
    due_at: str = ""
    due_rel: str = ""
    due_iso: str = ""
    url: str = ""
    course_id: int | None = None
    plannable_id: int | None = None
    points: float | None = None
    status_flags: list[str] = field(default_factory=list)
    raw_plannable: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON state storage."""
        return {
            "key": self.key,
            "_legacy_key": self.legacy_key,
            "ptype": self.ptype,
            "title": self.title,
            "course_code": self.course_code,
            "course_name": self.course_name,
            "due_at": self.due_at,
            "due_rel": self.due_rel,
            "due_iso": self.due_iso,
            "url": self.url,
            "course_id": self.course_id,
            "plannable_id": self.plannable_id,
            "points": self.points,
            "status_flags": self.status_flags,
            "raw_plannable": self.raw_plannable,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CanvasItem:
        """Deserialize from dict."""
        return cls(
            key=d.get("key", ""),
            legacy_key=d.get("_legacy_key", ""),
            ptype=d.get("ptype", ""),
            title=d.get("title", "(untitled)"),
            course_code=d.get("course_code", ""),
            course_name=d.get("course_name", ""),
            due_at=d.get("due_at", ""),
            due_rel=d.get("due_rel", ""),
            due_iso=d.get("due_iso", ""),
            url=d.get("url", ""),
            course_id=d.get("course_id"),
            plannable_id=d.get("plannable_id"),
            points=d.get("points"),
            status_flags=d.get("status_flags", []),
            raw_plannable=d.get("raw_plannable", {}),
        )