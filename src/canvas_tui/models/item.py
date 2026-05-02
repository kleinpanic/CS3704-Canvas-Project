"""CanvasItem — normalized planner/announcement item."""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from typing import Any

# Match scripts/generate_rerank_data.py:352-353 exactly so the SHA over
# RANK_PROMPT_TEMPLATE in canvas_tui.reranker stays equal to the
# TRAINING_PROMPT_FORMAT_SHA the GemmaReranker pipeline computed.
_BADGE_MAP: dict[str, str] = {
    "assignment": "ASGN",
    "quiz": "QUIZ",
    "exam": "EXAM",
    "discussion": "DISC",
    "event": "EVNT",
    "announcement": "NOTE",
}


def _anonymize_course(course_code: str) -> str:
    """Map a real course code (e.g. 'CS 3704') to the anonymized
    'COURSE\\d{4}' format the model was trained on.

    Deterministic SHA-256 → 4-digit modulo. Matches the v2 anonymization
    scheme used by the data-prep pipeline so consumers get the same
    `@COURSE####` strings that appeared at training time.
    """
    h = int(hashlib.sha256(course_code.strip().encode("utf-8")).hexdigest()[:8], 16)
    return f"COURSE{(h % 9000) + 1000}"


def _due_label(due_iso: str) -> str | None:
    """Convert an ISO8601 due timestamp to one of the four trained
    status tokens: OVERDUE / Today / Tomorrow / 'Due MM/DD HH:MM'.
    Returns None if `due_iso` is empty or unparseable (caller should
    omit the status field in that case)."""
    if not due_iso:
        return None
    try:
        dt = _dt.datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = _dt.datetime.now(_dt.timezone.utc)
    delta_h = (dt.astimezone(_dt.timezone.utc) - now).total_seconds() / 3600.0
    if delta_h < -1:
        return "OVERDUE"
    if delta_h < 24:
        return "Today"
    if delta_h < 48:
        return "Tomorrow"
    return f"Due {dt.strftime('%m/%d %H:%M')}"


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


def serialize_item(item: CanvasItem) -> str:
    """Serialize a CanvasItem to the trained format the published
    `kleinpanic93/gemma4-canvas-reranker` model expects.

    Format: ``[BADGE] Title @COURSE#### STATUS NNNpts``

    The course code is anonymized via SHA-256 → 4-digit modulo so that
    the consumer never sends a real institution-level course identifier
    to the model — matches the training-time anonymization scheme.

    Status is derived from `due_iso` (and `status_flags` for DONE):
        - DONE if "submitted" in status_flags
        - OVERDUE if past due
        - Today / Tomorrow / Due MM/DD HH:MM otherwise

    Returns a single-line string suitable for embedding in
    RANK_PROMPT_TEMPLATE (see canvas_tui.reranker).
    """
    parts: list[str] = []
    ptype = (item.ptype or "?").lower()
    parts.append(f"[{_BADGE_MAP.get(ptype, ptype[:4].upper())}]")
    parts.append((item.title or "(untitled)")[:45])
    if item.course_code:
        parts.append(f"@{_anonymize_course(item.course_code)}")
    if "submitted" in (item.status_flags or []):
        parts.append("DONE")
    else:
        label = _due_label(item.due_iso)
        if label:
            parts.append(label)
    if item.points:
        parts.append(f"{float(item.points):.0f}pts")
    return " ".join(parts)
