"""Canvas-side agent tools — read access to courses, assignments, syllabus, grades, announcements.

All tools use canvas_sdk.CanvasClient directly via CANVAS_TOKEN + CANVAS_BASE_URL env vars.
No canvas_tui dependency.
"""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "ListCourses",
    "GetAssignments",
    "GetCourse",
    "GetSyllabus",
    "GetTodo",
    "GetGrades",
    "ListAnnouncements",
    "ListPlannerItems",
]


def _client():
    from canvas_sdk import CanvasClient

    base_url = os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu")
    token = os.environ.get("CANVAS_TOKEN", "")
    if not token:
        raise RuntimeError("CANVAS_TOKEN environment variable is not set.")
    return CanvasClient(base_url, token)


class ListCourses:
    NAME = "canvas.list_courses"
    SCHEMA = {
        "name": NAME,
        "description": "List all enrolled courses for the current term.",
        "parameters": {
            "type": "object",
            "properties": {
                "active_only": {
                    "type": "boolean",
                    "description": "Only return courses with active enrollment (default true).",
                },
            },
            "required": [],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        c = _client()
        kwargs: dict[str, Any] = {"per_page": 100}
        if args.get("active_only", True):
            kwargs["enrollment_state"] = "active"
        return [
            {
                "id": course.id,
                "name": course.name,
                "course_code": course.course_code,
                "credits": course.extra_fields.get("credits"),
                "term": course.extra_fields.get("term", {}).get("name")
                if isinstance(course.extra_fields.get("term"), dict)
                else course.extra_fields.get("term"),
            }
            for course in c.get_courses(**kwargs)
        ]


class GetAssignments:
    NAME = "canvas.get_assignments"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Get upcoming assignments for one course or all active courses. "
            "Returns title, type, points_possible, due_iso, submitted, late, missing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": ["integer", "null"],
                    "description": "Course ID, or null for all active courses.",
                },
                "horizon_days": {
                    "type": "integer",
                    "default": 14,
                    "description": "Only return assignments due within the next N days.",
                },
                "include_submitted": {"type": "boolean", "default": False},
            },
            "required": [],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        import datetime as dt

        c = _client()
        horizon = int(args.get("horizon_days", 14))
        include_submitted = bool(args.get("include_submitted", False))
        cutoff = (dt.datetime.now(dt.UTC) + dt.timedelta(days=horizon)).isoformat()

        course_id = args.get("course_id")
        if course_id:
            courses = [c.get_course(int(course_id))]
        else:
            courses = c.get_courses(enrollment_state="active", per_page=100)

        results = []
        for course in courses:
            cid = course.id
            if not cid:
                continue
            for item in c.get_assignments(
                cid,
                bucket="upcoming",
                include=["submission"],
                per_page=100,
            ):
                due = item.due_at
                if due and due > cutoff:
                    continue
                sub = item.extra_fields.get("submission") or {}
                submitted = bool(
                    sub.get("submitted_at") if isinstance(sub, dict) else None
                )
                if not include_submitted and submitted:
                    continue
                results.append(
                    {
                        "id": item.id,
                        "title": item.name,
                        "course_id": cid,
                        "due_iso": due,
                        "points_possible": item.points_possible,
                        "submission_types": item.submission_types,
                        "submitted": submitted,
                        "late": sub.get("late", False) if isinstance(sub, dict) else False,
                        "missing": sub.get("missing", False) if isinstance(sub, dict) else False,
                    }
                )
        return results


class GetCourse:
    NAME = "canvas.get_course"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Get one course's metadata: name, code, credits (Canvas-reported if available), "
            "term, instructor list. If credits is null, call canvas.get_syllabus and "
            "parse the credit count from the syllabus text."
        ),
        "parameters": {
            "type": "object",
            "properties": {"course_id": {"type": "integer"}},
            "required": ["course_id"],
        },
    }

    @staticmethod
    def call(args: dict) -> dict:
        c = _client()
        course = c.get_course(
            int(args["course_id"]),
            include=["teachers", "term", "total_students"],
        )
        teachers_raw = course.extra_fields.get("teachers") or []
        teachers = [
            t.get("display_name", "") if isinstance(t, dict) else str(t) for t in teachers_raw
        ]
        term_raw = course.extra_fields.get("term")
        term_name = term_raw.get("name") if isinstance(term_raw, dict) else term_raw
        return {
            "id": course.id,
            "name": course.name,
            "course_code": course.course_code,
            "credits": course.extra_fields.get("credits"),
            "term": term_name,
            "instructors": teachers,
            "total_students": course.extra_fields.get("total_students"),
        }


class GetSyllabus:
    NAME = "canvas.get_syllabus"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Fetch a course's syllabus (HTML stripped to plain text). Use to understand "
            "course structure, exam dates, project milestones, and credit hours when "
            "canvas.get_course returns credits=null."
        ),
        "parameters": {
            "type": "object",
            "properties": {"course_id": {"type": "integer"}},
            "required": ["course_id"],
        },
    }

    @staticmethod
    def call(args: dict) -> str:
        import html
        import re

        c = _client()
        course = c.get_course(int(args["course_id"]), include=["syllabus_body"])
        raw = course.syllabus_body or ""
        text = re.sub(r"<[^>]+>", " ", raw)
        text = html.unescape(text)
        return re.sub(r"\s{2,}", " ", text).strip()


class GetTodo:
    NAME = "canvas.get_todo"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Fetch the student's Canvas todo/upcoming-events feed — assignments and quizzes that need attention soon."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        c = _client()
        out = []
        for item in c.get_todo_items():
            assignment = item.assignment or {}
            out.append(
                {
                    "type": item.type,
                    "course_id": item.course_id,
                    "title": assignment.get("name", "") if isinstance(assignment, dict) else "",
                    "due_iso": assignment.get("due_at") if isinstance(assignment, dict) else None,
                    "points_possible": assignment.get("points_possible") if isinstance(assignment, dict) else None,
                }
            )
        return out


class GetGrades:
    NAME = "canvas.get_grades"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Get the student's current grade (computed score 0-100) per active course. "
            "Use to weight urgency — courses with a low score need more study time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": ["integer", "null"],
                    "description": "Specific course ID, or null for all active courses.",
                },
            },
            "required": [],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        c = _client()
        course_id = args.get("course_id")
        if course_id:
            courses = [c.get_course(int(course_id), include=["total_scores"])]
        else:
            courses = c.get_courses(
                enrollment_state="active",
                include=["total_scores"],
                per_page=100,
            )
        results = []
        for course in courses:
            cid = course.id
            enrollments = course.extra_fields.get("enrollments") or []
            score = None
            for e in enrollments:
                e_dict = e if isinstance(e, dict) else {}
                for k in ("computed_current_score", "current_score", "computed_final_score"):
                    v = e_dict.get(k)
                    if v is not None:
                        score = float(v)
                        break
                if score is not None:
                    break
            results.append({"course_id": cid, "current_score": score})
        return results


class ListAnnouncements:
    NAME = "canvas.list_announcements"
    SCHEMA = {
        "name": NAME,
        "description": (
            "List recent course announcements. Use to catch exam rescheduling, "
            "extension grants, or changed due dates before scheduling study time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Course IDs to search. Empty = all active courses.",
                },
                "past_days": {
                    "type": "integer",
                    "default": 7,
                    "description": "How many days back to search.",
                },
            },
            "required": [],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        import datetime as dt

        c = _client()
        course_ids = [int(x) for x in (args.get("course_ids") or [])]
        if not course_ids:
            course_ids = [
                course.id
                for course in c.get_courses(enrollment_state="active", per_page=100)
                if course.id
            ]
        context_codes = [f"course_{cid}" for cid in course_ids]
        since = (dt.datetime.now(dt.UTC) - dt.timedelta(days=int(args.get("past_days", 7)))).isoformat()
        out = []
        for ann in c.get_announcements(context_codes=context_codes, start_date=since):
            posted = ann.posted_at
            context_code = ann.extra_fields.get("context_code", "")
            out.append(
                {
                    "id": ann.id,
                    "title": ann.title,
                    "course_id": context_code.removeprefix("course_") or None,
                    "posted_iso": posted,
                    "message_preview": (ann.message or "")[:300],
                }
            )
        return out


class ListPlannerItems:
    NAME = "canvas.list_planner_items"
    SCHEMA = {
        "name": NAME,
        "description": (
            "List Canvas planner items (student-created notes and override markers). "
            "Use to see what is already in the student's Canvas planner before "
            "proposing duplicate calendar blocks."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        c = _client()
        out = []
        for note in c.get_planner_notes():
            out.append(
                {
                    "id": note.id,
                    "title": note.title,
                    "todo_date": note.todo_date,
                    "course_id": note.course_id,
                    "details": note.details,
                }
            )
        return out
