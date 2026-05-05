"""
Tests for scripts/share_my_canvas.py

Verifies the anonymization logic, output format, and error handling
without making any real Canvas API calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import share_my_canvas  # noqa: E402


# ── Anonymization ─────────────────────────────────────────────────────────────


def test_hash_is_deterministic():
    h1 = share_my_canvas._hash("salt", "12345678")
    h2 = share_my_canvas._hash("salt", "12345678")
    assert h1 == h2


def test_hash_differs_by_salt():
    h1 = share_my_canvas._hash("salt_a", "12345678")
    h2 = share_my_canvas._hash("salt_b", "12345678")
    assert h1 != h2


def test_hash_format():
    result = share_my_canvas._hash("x", "999")
    assert result.startswith("ID")
    assert result[2:].isdigit()


def test_anon_course_mapping():
    share_my_canvas._COURSE_MAP.clear()
    share_my_canvas._COURSE_CTR[0] = 0
    c1 = share_my_canvas._anon_course("CS 3704")
    c2 = share_my_canvas._anon_course("ENGL 2204")
    c3 = share_my_canvas._anon_course("CS 3704")  # repeat
    assert c1 == "@COURSE1"
    assert c2 == "@COURSE2"
    assert c1 == c3  # same course → same anon code


def test_anonymize_strips_canvas_ids():
    share_my_canvas._COURSE_MAP.clear()
    share_my_canvas._COURSE_CTR[0] = 0
    obj = {"id": 12345678, "name": "Test Assignment"}
    result = share_my_canvas.anonymize(obj, "testsalt")
    out = json.dumps(result)
    assert "12345678" not in out
    assert "ID" in out


def test_anonymize_strips_course_codes():
    share_my_canvas._COURSE_MAP.clear()
    share_my_canvas._COURSE_CTR[0] = 0
    obj = {"course": "CS 3704 Software Engineering"}
    result = share_my_canvas.anonymize(obj, "salt")
    out = json.dumps(result)
    assert "CS 3704" not in out
    assert "COURSE" in out


def test_anonymize_preserves_dates():
    share_my_canvas._COURSE_MAP.clear()
    share_my_canvas._COURSE_CTR[0] = 0
    obj = {"due_at": "2026-05-10T23:59:00Z", "points": 100}
    result = share_my_canvas.anonymize(obj, "salt")
    assert result["due_at"] == "2026-05-10T23:59:00Z"
    assert result["points"] == 100


# ── CLI / env guard ───────────────────────────────────────────────────────────


def test_missing_token_exits(monkeypatch):
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        share_my_canvas._token()
    assert exc.value.code == 1


def test_token_returned_from_env(monkeypatch):
    monkeypatch.setenv("CANVAS_TOKEN", "test-abc-123")
    assert share_my_canvas._token() == "test-abc-123"


# ── collect() — mocked HTTP ───────────────────────────────────────────────────

FAKE_COURSES = [
    {"id": 98765432, "name": "CS 3704 Software Engineering", "course_code": "CS3704", "term": {"name": "Spring 2026"}},
]
FAKE_ASSIGNMENTS = [
    {
        "name": "Homework 1",
        "due_at": "2026-05-15T23:59:00Z",
        "points_possible": 100,
        "submission_types": ["online_upload"],
        "submission": {"submitted_at": None, "graded_at": None, "workflow_state": "unsubmitted"},
    },
]
FAKE_TODOS = [
    {
        "type": "submitting",
        "assignment": {"name": "Homework 1", "due_at": "2026-05-15T23:59:00Z"},
        "course_id": 98765432,
    },
]


def _mock_get(path, params=None):
    # collect() calls /courses once per enrollment state — return same list each time,
    # dedup by id is handled inside collect()
    if path == "/courses":
        return FAKE_COURSES
    if "/assignments" in path:
        return FAKE_ASSIGNMENTS
    if path == "/users/self/todo_items":
        return FAKE_TODOS
    return []


def test_collect_produces_anonymized_records(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
    monkeypatch.setattr(share_my_canvas, "_get", _mock_get)
    share_my_canvas._COURSE_MAP.clear()
    share_my_canvas._COURSE_CTR[0] = 0

    records = share_my_canvas.collect("testuser")

    assert len(records) >= 1
    dumped = json.dumps(records)
    assert "98765432" not in dumped, "Canvas ID should be anonymized"
    assert "CS 3704" not in dumped, "Course code should be anonymized"
    assert "testuser" in dumped, "Contributor ID should be present"
    assert "@COURSE" in dumped, "Anonymized course should use @COURSE prefix"


def test_collect_assignments_have_submission_status(monkeypatch):
    monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
    monkeypatch.setattr(share_my_canvas, "_get", _mock_get)
    share_my_canvas._COURSE_MAP.clear()
    share_my_canvas._COURSE_CTR[0] = 0

    records = share_my_canvas.collect("testuser")
    course_snaps = [r for r in records if r.get("type") == "course_snapshot"]
    assert course_snaps, "Expected at least one course_snapshot"
    for snap in course_snaps:
        for asgn in snap.get("assignments", []):
            assert "submission_status" in asgn, "Each assignment must have submission_status"
            assert asgn["submission_status"] in ("GRADED", "SUBMITTED", "NOT_SUBMITTED")


def test_collect_writes_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
    monkeypatch.setattr(share_my_canvas, "_get", _mock_get)
    share_my_canvas._COURSE_MAP.clear()
    share_my_canvas._COURSE_CTR[0] = 0

    out_file = tmp_path / "testuser.jsonl"
    records = share_my_canvas.collect("testuser")
    with open(out_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    lines = out_file.read_text().strip().splitlines()
    assert len(lines) >= 1
    for line in lines:
        obj = json.loads(line)
        assert "type" in obj
        assert "contributor_id" in obj
