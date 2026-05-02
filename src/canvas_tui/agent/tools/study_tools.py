"""Study-planning helpers — pure-code implementations of the
neuroscience-grounded heuristics in the system prompt. Exposed as tools
so the model can ask for a spaced-repetition schedule without having to
do the date arithmetic itself.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

__all__ = ["SpacedSchedule", "DeepBlockSize", "ExamBracket"]


class SpacedSchedule:
    NAME = "study.spaced_schedule"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Compute spaced-repetition session dates for an exam, applying the "
            "Cepeda et al. 2008 / Karpicke 2007 spacing rules. Returns 3-5 "
            "session datetimes with the first session 7-14 days before the exam."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exam_iso": {"type": "string", "description": "ISO8601 exam datetime."},
                "n_sessions": {"type": "integer", "default": 4, "description": "Target number of sessions (3-5 typical)."},
                "minutes_per_session": {"type": "integer", "default": 90},
                "preferred_hour": {"type": "integer", "default": 9, "description": "Preferred start hour (24h, default 9am for morning peak cognition)."},
            },
            "required": ["exam_iso"],
        },
    }
    @staticmethod
    def call(args: dict) -> list[dict]:
        exam = dt.datetime.fromisoformat(args["exam_iso"].replace("Z", "+00:00"))
        n = max(3, min(5, args.get("n_sessions", 4)))
        minutes = args.get("minutes_per_session", 90)
        hour = args.get("preferred_hour", 9)
        # Spacing: first session 7-14 days before; each subsequent halves the gap
        # roughly (expanding-spacing schedule). For n=4: -10, -5, -3, -1 days.
        gaps_by_n = {3: [10, 4, 1], 4: [10, 5, 2, 1], 5: [14, 7, 3, 2, 1]}
        gaps = gaps_by_n[n]
        sessions = []
        for g in gaps:
            t = (exam - dt.timedelta(days=g)).replace(hour=hour, minute=0, second=0, microsecond=0)
            sessions.append({
                "start_iso": t.isoformat(),
                "end_iso": (t + dt.timedelta(minutes=minutes)).isoformat(),
                "label": f"Exam prep session — {g}d before",
                "minutes": minutes,
            })
        return sessions


class DeepBlockSize:
    NAME = "study.recommend_block_size"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Recommend the right block size (in minutes) for a task type, based on "
            "deep-work + cognitive-load research. Returns the recommended duration "
            "and a brief rationale."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": ["writing", "problem_set", "exam_prep", "reading", "review", "admin", "discussion", "project_work"],
                },
            },
            "required": ["task_type"],
        },
    }
    @staticmethod
    def call(args: dict) -> dict:
        rec = {
            "writing":      (90, "deep cognitive work — peak ~90min, hard cap before fatigue"),
            "problem_set":  (90, "sustained reasoning — 60-90min blocks; 25min for trivial sets"),
            "exam_prep":    (90, "comprehensive recall + practice — 90min with 15min breaks"),
            "reading":      (45, "moderate cognitive load — 45min blocks, more frequent breaks"),
            "review":       (45, "lighter than first-pass learning"),
            "admin":        (25, "Pomodoro-style — short shallow work"),
            "discussion":   (60, "structured dialogue — 60min canonical class length"),
            "project_work": (90, "deep work — 90min blocks, group adjacent if possible"),
        }
        minutes, rationale = rec[args["task_type"]]
        return {"minutes": minutes, "rationale": rationale}


class ExamBracket:
    NAME = "study.exam_bracket"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Generate the 'exam-day bracket' — a 30-60min low-load review block "
            "before the exam (no heavy cramming) and a 30min decompression block "
            "after (no other deep work)."
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
        review = args.get("review_minutes", 45)
        return [
            {
                "label": "Exam-day light review (no new material)",
                "start_iso": (start - dt.timedelta(minutes=review + 15)).isoformat(),
                "end_iso":   (start - dt.timedelta(minutes=15)).isoformat(),
            },
            {
                "label": "Decompress (no other deep work)",
                "start_iso": end.isoformat(),
                "end_iso":   (end + dt.timedelta(minutes=30)).isoformat(),
            },
        ]
