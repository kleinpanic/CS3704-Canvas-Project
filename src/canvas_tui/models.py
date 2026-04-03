"""Data models for Canvas TUI — typed dataclasses replacing raw dicts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CanvasItem:
    """A normalized planner/announcement item."""

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


@dataclass
class CourseInfo:
    """Minimal course info from the API."""

    course_id: int = 0
    course_code: str = ""
    name: str = ""


@dataclass
class ModalContext:
    """Context for tracking pending modal screens — uses UUID instead of id(screen)."""

    modal_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: str = ""
    ctx: dict[str, Any] = field(default_factory=dict)
