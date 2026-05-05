"""
Tests for scripts/convert_canvas_contributions.py

Verifies type mapping, status calculation, deduplication, file conversion,
and round-trip compatibility with share_my_canvas.py output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import convert_canvas_contributions as cc  # noqa: E402
import share_my_canvas as smc  # noqa: E402


# ── _item_type ─────────────────────────────────────────────────────────────────


def test_item_type_quiz():
    assert cc._item_type(["online_quiz"]) == "QUIZ"


def test_item_type_upload():
    assert cc._item_type(["online_upload"]) == "ASGN"


def test_item_type_discussion():
    assert cc._item_type(["discussion_topic"]) == "DISC"


def test_item_type_text_entry():
    assert cc._item_type(["online_text_entry"]) == "ASGN"


def test_item_type_media():
    assert cc._item_type(["media_recording"]) == "ASGN"


def test_item_type_none_literal():
    assert cc._item_type(["none"]) == "ASGN"


def test_item_type_unknown_defaults_to_asgn():
    assert cc._item_type(["some_future_type"]) == "ASGN"


def test_item_type_empty_defaults_to_asgn():
    assert cc._item_type([]) == "ASGN"


def test_item_type_takes_first_known():
    assert cc._item_type(["online_quiz", "online_upload"]) == "QUIZ"


# ── _offset_to_status ──────────────────────────────────────────────────────────


def test_status_overdue():
    assert cc._offset_to_status(-1) == "OVERDUE"


def test_status_overdue_large_negative():
    assert cc._offset_to_status(-30) == "OVERDUE"


def test_status_tomorrow():
    assert cc._offset_to_status(1) == "Tomorrow"


def test_status_days():
    assert cc._offset_to_status(7) == "7d"


def test_status_zero():
    assert cc._offset_to_status(0) == "0d"


# ── _item_key ──────────────────────────────────────────────────────────────────


def test_item_key_deterministic():
    k1 = cc._item_key("ASGN", "Homework 1", "@COURSE1")
    k2 = cc._item_key("ASGN", "Homework 1", "@COURSE1")
    assert k1 == k2


def test_item_key_differs_by_title():
    k1 = cc._item_key("ASGN", "Homework 1", "@COURSE1")
    k2 = cc._item_key("ASGN", "Homework 2", "@COURSE1")
    assert k1 != k2


def test_item_key_differs_by_course():
    k1 = cc._item_key("ASGN", "Homework 1", "@COURSE1")
    k2 = cc._item_key("ASGN", "Homework 1", "@COURSE2")
    assert k1 != k2


def test_item_key_differs_by_type():
    k1 = cc._item_key("ASGN", "Project", "@COURSE1")
    k2 = cc._item_key("QUIZ", "Project", "@COURSE1")
    assert k1 != k2


def test_item_key_strips_title_whitespace():
    k1 = cc._item_key("ASGN", "  Homework 1  ", "@COURSE1")
    k2 = cc._item_key("ASGN", "Homework 1", "@COURSE1")
    assert k1 == k2


def test_item_key_length():
    k = cc._item_key("ASGN", "Homework 1", "@COURSE1")
    assert len(k) == 12


# ── convert_file ───────────────────────────────────────────────────────────────


def _make_snapshot(tmp_path, **overrides):
    base = {
        "type": "course_snapshot",
        "course_code": "@COURSE1",
        "course_name": "@COURSE1 Introduction",
        "term": "Fall 2025",
        "assignments": [
            {
                "name": "Project 1",
                "due_at": "2026-06-01T23:59:00Z",
                "points_possible": 100,
                "submission_types": ["online_upload"],
                "submission_status": "NOT_SUBMITTED",
            }
        ],
        "contributor_id": "testuser",
        "collected_at": "2026-05-01T00:00:00Z",
    }
    base.update(overrides)
    f = tmp_path / "testuser.jsonl"
    f.write_text(json.dumps(base) + "\n")
    return f


def test_convert_file_basic(tmp_path):
    f = _make_snapshot(tmp_path)
    items = cc.convert_file(f, set())
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "ASGN"
    assert item["title"] == "Project 1"
    assert item["points"] == 100.0
    assert item["contributor"] == "testuser"
    assert item["source"] == f"collab:{f.name}"


def test_convert_file_skips_non_snapshot(tmp_path):
    f = tmp_path / "todo.jsonl"
    f.write_text(
        json.dumps(
            {"type": "todo_snapshot", "items": [], "contributor_id": "x", "collected_at": "2026-05-01T00:00:00Z"}
        )
        + "\n"
    )
    items = cc.convert_file(f, set())
    assert items == []


def test_convert_file_skips_zero_points(tmp_path):
    f = _make_snapshot(
        tmp_path,
        assignments=[
            {
                "name": "Ungraded",
                "due_at": "2026-06-01T00:00:00Z",
                "points_possible": 0,
                "submission_types": ["none"],
            }
        ],
    )
    items = cc.convert_file(f, set())
    assert items == []


def test_convert_file_skips_null_points(tmp_path):
    f = _make_snapshot(
        tmp_path,
        assignments=[
            {
                "name": "No Points",
                "due_at": "2026-06-01T00:00:00Z",
                "points_possible": None,
                "submission_types": ["online_upload"],
            }
        ],
    )
    items = cc.convert_file(f, set())
    assert items == []


def test_convert_file_skips_missing_title(tmp_path):
    f = _make_snapshot(
        tmp_path,
        assignments=[
            {
                "name": "",
                "due_at": "2026-06-01T00:00:00Z",
                "points_possible": 100,
                "submission_types": ["online_upload"],
            }
        ],
    )
    items = cc.convert_file(f, set())
    assert items == []


def test_convert_file_deduplication(tmp_path):
    f = _make_snapshot(tmp_path)
    seen = set()
    items1 = cc.convert_file(f, seen)
    assert len(items1) == 1
    items2 = cc.convert_file(f, seen)
    assert len(items2) == 0  # already in seen


def test_convert_file_course_gets_at_prefix(tmp_path):
    f = _make_snapshot(tmp_path, course_code="CS3704")
    items = cc.convert_file(f, set())
    assert items[0]["course"].startswith("@")


def test_convert_file_due_offset_days(tmp_path):
    f = _make_snapshot(tmp_path)
    items = cc.convert_file(f, set())
    assert items[0]["due_offset_days"] == 31  # 2026-06-01 - 2026-05-01 = 31


def test_convert_file_status_derived_from_offset(tmp_path):
    f = _make_snapshot(tmp_path)
    items = cc.convert_file(f, set())
    assert items[0]["status"] == "31d"


def test_convert_file_overdue_status(tmp_path):
    f = _make_snapshot(
        tmp_path,
        assignments=[
            {
                "name": "Old Homework",
                "due_at": "2026-04-01T00:00:00Z",
                "points_possible": 50,
                "submission_types": ["online_upload"],
            }
        ],
    )
    items = cc.convert_file(f, set())
    assert items[0]["status"] == "OVERDUE"


def test_convert_file_missing_due_defaults_to_3d(tmp_path):
    f = _make_snapshot(
        tmp_path,
        assignments=[
            {
                "name": "No Due Date",
                "due_at": None,
                "points_possible": 50,
                "submission_types": ["online_upload"],
            }
        ],
    )
    items = cc.convert_file(f, set())
    assert items[0]["status"] == "3d"


def test_convert_file_multiple_assignments(tmp_path):
    f = _make_snapshot(
        tmp_path,
        assignments=[
            {
                "name": "HW1",
                "due_at": "2026-06-01T00:00:00Z",
                "points_possible": 50,
                "submission_types": ["online_upload"],
            },
            {
                "name": "HW2",
                "due_at": "2026-06-05T00:00:00Z",
                "points_possible": 75,
                "submission_types": ["online_quiz"],
            },
            {
                "name": "HW3",
                "due_at": "2026-06-10T00:00:00Z",
                "points_possible": 100,
                "submission_types": ["discussion_topic"],
            },
        ],
    )
    items = cc.convert_file(f, set())
    assert len(items) == 3
    types = {i["type"] for i in items}
    assert "ASGN" in types
    assert "QUIZ" in types
    assert "DISC" in types


def test_convert_file_item_id_in_output(tmp_path):
    f = _make_snapshot(tmp_path)
    items = cc.convert_file(f, set())
    assert "item_id" in items[0]
    assert len(items[0]["item_id"]) == 12


# ── Round-trip: share_my_canvas → convert_canvas_contributions ─────────────────


def test_round_trip_compatible_with_share_my_canvas(tmp_path, monkeypatch):
    smc._COURSE_MAP.clear()
    smc._COURSE_CTR[0] = 0

    raw_record = {
        "type": "course_snapshot",
        "course_code": "CS3704",
        "course_name": "CS3704 Software Engineering",
        "term": "Spring 2026",
        "assignments": [
            {
                "name": "Project 4",
                "type": "ASGN",
                "due_at": "2026-06-01T23:59:00Z",
                "points_possible": 150,
                "submission_types": ["online_upload"],
                "submission_status": "NOT_SUBMITTED",
            }
        ],
        "contributor_id": "testuser",
        "collected_at": "2026-05-01T00:00:00Z",
    }

    anonymized = smc.anonymize(raw_record, "testuser")
    out = tmp_path / "testuser.jsonl"
    out.write_text(json.dumps(anonymized) + "\n")

    items = cc.convert_file(out, set())
    assert len(items) == 1

    dumped = json.dumps(items[0])
    assert "CS3704" not in dumped, "Original course code must not appear after round-trip"
    assert items[0]["course"].startswith("@"), "Course must be anonymized @COURSEn token"
    assert items[0]["type"] == "ASGN"
    assert items[0]["points"] == 150.0
    assert items[0]["contributor"] == "testuser"
