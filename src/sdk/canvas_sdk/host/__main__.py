"""
Chrome Native Messaging host for Canvas Tracker.

Chrome pipes JSON messages through stdin/stdout using a 4-byte little-endian
length prefix per message. This process reads those messages, calls the Python
SDK, and writes back JSON responses in the same format.

Usage (Chrome registers this via the host manifest):
  python -m canvas_sdk.host
"""

import dataclasses
import json
import struct
import sys
from typing import Any

from canvas_sdk.client import CanvasClient

# ── Serialization ─────────────────────────────────────────────────────────────


def _serialize(obj: Any) -> Any:
    """Recursively convert dataclasses / plain objects to plain dicts/lists."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {}
        for f in dataclasses.fields(obj):
            if f.name == "extra_fields":
                for ek, ev in (getattr(obj, "extra_fields", None) or {}).items():
                    out[ek] = _serialize(ev)
            else:
                out[f.name] = _serialize(getattr(obj, f.name))
        return out
    # Plain object — attrs are instance vars; skip private + _date variants
    if hasattr(obj, "__dict__"):
        out = {}
        for k, v in vars(obj).items():
            if k.startswith("_") or k.endswith("_date"):
                continue
            out[k] = _serialize(v)
        return out
    return str(obj)


def _drain(paginated, limit: int = 100) -> list:
    """Pull up to `limit` items from a list/iterable and serialize."""
    results = []
    for item in paginated:
        results.append(_serialize(item))
        if len(results) >= limit:
            break
    return results


# ── Message I/O (Chrome native messaging wire format) ─────────────────────────


def _read() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    length = struct.unpack("<I", raw)[0]
    data = sys.stdin.buffer.read(length)
    return json.loads(data.decode("utf-8"))


def _write(msg: dict) -> None:
    encoded = json.dumps(msg, default=str).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


# ── Dispatch ──────────────────────────────────────────────────────────────────


def _handle(msg: dict) -> dict:
    method = msg.get("method")
    token = msg.get("token")
    base_url = msg.get("baseUrl", "https://canvas.vt.edu")
    params = msg.get("params", {})

    if not token:
        return {"ok": False, "error": "No token"}

    canvas = CanvasClient(base_url, token)

    if method == "getUser":
        user = canvas.get_current_user()
        return {"ok": True, "data": _serialize(user)}

    if method == "validateToken":
        user = canvas.get_current_user()
        return {"ok": True, "user": _serialize(user)}

    if method == "getCourses":
        courses = canvas.get_courses(
            enrollment_state="active",
            include=["teachers"],
            per_page=100,
        )
        return {"ok": True, "data": _drain(courses)}

    if method == "getUpcomingAssignments":
        events = canvas.get_upcoming_events()
        return {"ok": True, "data": _drain(events)}

    if method == "getTodo":
        items = canvas.get_todo_items()
        return {"ok": True, "data": _drain(items)}

    if method == "getPlannerNotes":
        notes = canvas.get_planner_notes()
        return {"ok": True, "data": _drain(notes)}

    course_id = params.get("courseId")
    if not course_id and method.startswith("getCourse"):
        return {"ok": False, "error": "courseId required"}

    if method == "getCourseAssignments":
        assignments = canvas.get_assignments(
            course_id,
            include=["submission"],
            per_page=50,
        )
        return {"ok": True, "data": _drain(assignments)}

    if method == "getCourseGrades":
        enrollments = canvas.get_enrollments(
            course_id,
            user_id="self",
            include=["current_points", "final_grade"],
        )
        return {"ok": True, "data": _drain(enrollments)}

    if method == "getCourseAnnouncements":
        topics = canvas.get_discussion_topics(course_id, only_announcements=True)
        return {"ok": True, "data": _drain(topics)}

    if method == "getCourseModules":
        modules = canvas.get_modules(course_id)
        return {"ok": True, "data": _drain(modules)}

    if method == "getCourseFiles":
        files = canvas.get_files(course_id)
        return {"ok": True, "data": _drain(files)}

    return {"ok": False, "error": f"Unknown method: {method}"}


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    while True:
        try:
            msg = _read()
            if msg is None:
                break
            result = _handle(msg)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        _write(result)


if __name__ == "__main__":
    main()
