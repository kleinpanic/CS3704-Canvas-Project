# SPDX-License-Identifier: GPL-3.0-or-later
"""Study-planning tools — neuroscience-grounded heuristics exposed as agent functions.

All implementations are pure Python with no external dependencies.
"""

from __future__ import annotations

import datetime as dt

__all__ = ["SpacedSchedule", "SemesterSchedule", "DeepBlockSize", "ExamBracket"]


class SpacedSchedule:
    NAME = "study.spaced_schedule"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Compute spaced-repetition session dates for an upcoming exam using "
            "Cepeda et al. 2008 spacing rules. Returns 3-5 session blocks starting "
            "7-14 days before the exam."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exam_iso": {"type": "string", "description": "ISO8601 exam datetime."},
                "n_sessions": {
                    "type": "integer",
                    "default": 4,
                    "description": "Number of study sessions (3-5).",
                },
                "minutes_per_session": {"type": "integer", "default": 90},
                "preferred_hour": {
                    "type": "integer",
                    "default": 9,
                    "description": "Preferred start hour (24h). 9 = 9am morning-peak cognition.",
                },
            },
            "required": ["exam_iso"],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        exam = dt.datetime.fromisoformat(args["exam_iso"].replace("Z", "+00:00"))
        n = max(3, min(5, int(args.get("n_sessions", 4))))
        minutes = int(args.get("minutes_per_session", 90))
        hour = int(args.get("preferred_hour", 9))
        gaps_by_n = {3: [10, 4, 1], 4: [10, 5, 2, 1], 5: [14, 7, 3, 2, 1]}
        sessions = []
        for g in gaps_by_n[n]:
            t = (exam - dt.timedelta(days=g)).replace(hour=hour, minute=0, second=0, microsecond=0)
            sessions.append(
                {
                    "start_iso": t.isoformat(),
                    "end_iso": (t + dt.timedelta(minutes=minutes)).isoformat(),
                    "label": f"Exam prep — {g}d before",
                    "minutes": minutes,
                }
            )
        return sessions


class SemesterSchedule:
    NAME = "study.semester_schedule"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Generate a long-horizon semester work schedule for a project-heavy course. "
            "Distributes work blocks across the remaining semester, ramping intensity "
            "toward major deadlines. Returns weekly recommended hour counts and key "
            "milestone dates. Use for courses where a single final project dominates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "semester_end_iso": {
                    "type": "string",
                    "description": "ISO8601 last day of the semester / course end date.",
                },
                "deadlines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "due_iso": {"type": "string"},
                            "estimated_hours": {"type": "integer"},
                        },
                        "required": ["title", "due_iso", "estimated_hours"],
                    },
                    "description": "Named milestones with estimated work hours.",
                },
                "weekly_hours_available": {
                    "type": "integer",
                    "default": 10,
                    "description": "Hours per week the student can dedicate to this course.",
                },
                "ramp_factor": {
                    "type": "number",
                    "default": 1.5,
                    "description": (
                        "Effort multiplier for the final 25% of remaining time "
                        "(1.0 = flat distribution, 1.5 = 50% heavier near deadline)."
                    ),
                },
            },
            "required": ["semester_end_iso", "deadlines"],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        now = dt.datetime.now(dt.UTC)
        end = dt.datetime.fromisoformat(args["semester_end_iso"].replace("Z", "+00:00"))
        deadlines = sorted(
            args.get("deadlines", []),
            key=lambda d: d["due_iso"],
        )
        weekly_hours = int(args.get("weekly_hours_available", 10))
        ramp = float(args.get("ramp_factor", 1.5))

        total_days = max(1, (end - now).days)
        ramp_cutoff = total_days * 0.75

        result = []
        for dl in deadlines:
            due = dt.datetime.fromisoformat(dl["due_iso"].replace("Z", "+00:00"))
            days_left = max(1, (due - now).days)
            est = int(dl["estimated_hours"])

            if days_left <= total_days * 0.25:
                hours_per_week = min(weekly_hours * ramp, weekly_hours * 2)
            else:
                hours_per_week = weekly_hours

            weeks_available = days_left / 7
            weeks_needed = est / hours_per_week if hours_per_week > 0 else weeks_available
            start_work_date = due - dt.timedelta(weeks=min(weeks_needed, weeks_available))

            result.append(
                {
                    "milestone": dl["title"],
                    "due_iso": dl["due_iso"],
                    "estimated_hours": est,
                    "start_work_iso": start_work_date.isoformat(),
                    "recommended_hours_per_week": round(hours_per_week, 1),
                    "weeks_allocated": round(min(weeks_needed, weeks_available), 1),
                    "intensity": "high" if days_left < ramp_cutoff else "normal",
                }
            )

        return result


class DeepBlockSize:
    NAME = "study.recommend_block_size"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Recommend the right work block length (minutes) for a task type based on "
            "deep-work and cognitive-load research."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": [
                        "writing",
                        "problem_set",
                        "exam_prep",
                        "reading",
                        "review",
                        "admin",
                        "discussion",
                        "project_work",
                        "lab",
                    ],
                },
            },
            "required": ["task_type"],
        },
    }

    @staticmethod
    def call(args: dict) -> dict:
        recs = {
            "writing": (90, "deep cognitive work — 90min peak, hard cap before fatigue"),
            "problem_set": (90, "sustained reasoning — 60-90min; 25min for trivial sets"),
            "exam_prep": (90, "recall + practice — 90min with 15min breaks"),
            "reading": (45, "moderate load — 45min blocks, frequent breaks"),
            "review": (45, "lighter than first-pass learning"),
            "admin": (25, "Pomodoro-style — short shallow work"),
            "discussion": (60, "structured dialogue — canonical 60min class length"),
            "project_work": (90, "deep work — 90min blocks, group adjacent if possible"),
            "lab": (120, "hands-on work — longer blocks to account for setup/teardown"),
        }
        minutes, rationale = recs[args["task_type"]]
        return {"minutes": minutes, "rationale": rationale}


class ExamBracket:
    NAME = "study.exam_bracket"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Generate the exam-day bracket: a light review block before the exam "
            "(no heavy cramming) and a decompression block after (no other deep work)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exam_start_iso": {"type": "string"},
                "exam_end_iso": {"type": "string"},
                "review_minutes": {"type": "integer", "default": 45},
            },
            "required": ["exam_start_iso", "exam_end_iso"],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        start = dt.datetime.fromisoformat(args["exam_start_iso"].replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(args["exam_end_iso"].replace("Z", "+00:00"))
        review = int(args.get("review_minutes", 45))
        return [
            {
                "label": "Exam-day light review (no new material)",
                "start_iso": (start - dt.timedelta(minutes=review + 15)).isoformat(),
                "end_iso": (start - dt.timedelta(minutes=15)).isoformat(),
            },
            {
                "label": "Decompress — no other deep work",
                "start_iso": end.isoformat(),
                "end_iso": (end + dt.timedelta(minutes=30)).isoformat(),
            },
        ]
