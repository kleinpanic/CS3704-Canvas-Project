"""Canvas-side tools — read-only access to courses, assignments, syllabi, TODOs."""
from __future__ import annotations

from typing import Any

__all__ = ["ListCourses", "GetAssignments", "GetTodo", "GetSyllabus", "GetCourse"]


class ListCourses:
    NAME = "canvas.list_courses"
    SCHEMA = {
        "name": NAME,
        "description": "List all the student's enrolled courses for the current term.",
        "parameters": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean", "description": "If True (default), only courses with a current enrollment."},
            },
            "required": [],
        },
    }
    @staticmethod
    def call(args: dict) -> list[dict]:
        from canvas_tui.api import CanvasAPI
        api = CanvasAPI.from_config()
        active = args.get("active_only", True)
        return [c.to_dict() for c in api.list_courses(active_only=active)]


class GetAssignments:
    NAME = "canvas.get_assignments"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Get assignments for one course or all courses, with optional time-window filter. "
            "Returns title, type, points, due_iso, status_flags, course_code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": ["integer", "null"], "description": "Course ID, or null for all courses."},
                "horizon_days": {"type": "integer", "default": 14, "description": "Window: due in next N days."},
                "include_submitted": {"type": "boolean", "default": False},
            },
            "required": [],
        },
    }
    @staticmethod
    def call(args: dict) -> list[dict]:
        from canvas_tui.api import CanvasAPI
        api = CanvasAPI.from_config()
        items = api.get_assignments(
            course_id=args.get("course_id"),
            horizon_days=args.get("horizon_days", 14),
            include_submitted=args.get("include_submitted", False),
        )
        return [it.to_dict() for it in items]


class GetTodo:
    NAME = "canvas.get_todo"
    SCHEMA = {
        "name": NAME,
        "description": "Fetch the student's Canvas TODO list (the official 'what needs your attention' feed).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    @staticmethod
    def call(args: dict) -> list[dict]:
        from canvas_tui.api import CanvasAPI
        api = CanvasAPI.from_config()
        return [t.to_dict() for t in api.get_todo()]


class GetSyllabus:
    NAME = "canvas.get_syllabus"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Fetch a course's syllabus (HTML stripped to text). Use to understand the "
            "course shape: weekly schedule, exam dates, project structure, weighting."
        ),
        "parameters": {
            "type": "object",
            "properties": {"course_id": {"type": "integer"}},
            "required": ["course_id"],
        },
    }
    @staticmethod
    def call(args: dict) -> str:
        from canvas_tui.api import CanvasAPI
        api = CanvasAPI.from_config()
        return api.get_syllabus(args["course_id"])


class GetCourse:
    NAME = "canvas.get_course"
    SCHEMA = {
        "name": NAME,
        "description": "Get one course's metadata (name, code, credit hours if exposed, term, instructor).",
        "parameters": {
            "type": "object",
            "properties": {"course_id": {"type": "integer"}},
            "required": ["course_id"],
        },
    }
    @staticmethod
    def call(args: dict) -> dict:
        from canvas_tui.api import CanvasAPI
        api = CanvasAPI.from_config()
        return api.get_course(args["course_id"]).to_dict()
