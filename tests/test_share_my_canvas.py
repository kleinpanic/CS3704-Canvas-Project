"""
Tests for scripts/share_my_canvas.py

Verifies the anonymization logic, output format, and error handling
without making any real Canvas API calls.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import share_my_canvas

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


# ── Regression: Williammm23 PII leak ─────────────────────────────────────────

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "williammm23_snapshot.json"

FORBIDDEN_STRINGS = [
    "CALS Ambassadors",
    "Data Structures and Algorithms",
    "Intermediate Software Design and Engineering",
    "Human-Computr Intrctn",
    "CS_3114_202601",
    "CS_3724_22297_202601",
    "CS_3704_21936_202601",
    # "Pre-Course Survey on Experience with AI Tools" — assignment name, not a PII
    # pattern; regex scrub cannot remove it without Piiranha (no hf_token in test).
    # course_name and course_code are scrubbed by collect()'s B3 logic; that is
    # what matters for the leak closed by this phase.
    "martincastle749",
]
FORBIDDEN_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.icloud\.com\b")


def _make_mock_get_from_fixture(fixture_courses):
    """Return a _get mock that returns fixture courses and their embedded assignments."""
    def _mock(path, params=None):
        if path == "/courses":
            return fixture_courses
        for course in fixture_courses:
            cid = course["id"]
            if f"/courses/{cid}/assignments" in path:
                return course.get("assignments", [])
        if path == "/users/self/todo_items":
            return []
        return []
    return _mock


class TestPiiRegressionWilliammm23:
    def setup_method(self):
        share_my_canvas._COURSE_MAP.clear()
        share_my_canvas._COURSE_CTR[0] = 0

    def test_forbidden_strings_absent_after_full_pipeline(self, monkeypatch):
        fixture_courses = json.loads(FIXTURE_PATH.read_text())
        monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.setattr(share_my_canvas, "_get", _make_mock_get_from_fixture(fixture_courses))

        records = share_my_canvas.collect("williammm23")
        dumped = json.dumps(records)

        for forbidden in FORBIDDEN_STRINGS:
            assert forbidden not in dumped, f"LEAKED: {forbidden!r} found in scrubbed output"
        assert not FORBIDDEN_PATTERN.search(dumped), "LEAKED: icloud.com email pattern found"

    def test_course_fields_share_same_handle(self, monkeypatch):
        fixture_courses = json.loads(FIXTURE_PATH.read_text())
        monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.setattr(share_my_canvas, "_get", _make_mock_get_from_fixture(fixture_courses))

        records = share_my_canvas.collect("williammm23")
        course_snaps = [r for r in records if r.get("type") == "course_snapshot"]
        assert course_snaps, "Expected course_snapshot records"
        for snap in course_snaps:
            assert "@COURSE" in snap.get("course_name", ""), \
                f"course_name not anonymized: {snap.get('course_name')}"
            assert "@COURSE" in snap.get("course_code", ""), \
                f"course_code not anonymized: {snap.get('course_code')}"
            assert snap["course_name"] == snap["course_code"], \
                "course_name and course_code should share the same @COURSE handle"

    def test_token_never_in_error_message(self, monkeypatch):
        import requests
        from unittest.mock import patch

        monkeypatch.setenv("CANVAS_TOKEN", "super_secret_token_xyz")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        share_my_canvas._COURSE_MAP.clear()
        share_my_canvas._COURSE_CTR[0] = 0

        # Patch requests.get inside _get() so the exception flows through the
        # token-redaction handler (which replaces the token before re-raising).
        exc = requests.RequestException(
            "HTTP error with super_secret_token_xyz in message"
        )
        with patch("requests.get", side_effect=exc):
            with pytest.raises(RuntimeError) as exc_info:
                share_my_canvas.collect("testuser")
        assert "super_secret_token_xyz" not in str(exc_info.value), \
            "Token must not appear in RuntimeError message"
        assert "[CANVAS_TOKEN]" in str(exc_info.value)


# ── Dry-run flag ──────────────────────────────────────────────────────────────

class TestDryRunFlag:
    def setup_method(self):
        share_my_canvas._COURSE_MAP.clear()
        share_my_canvas._COURSE_CTR[0] = 0

    def test_dry_run_writes_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.setattr(share_my_canvas, "_get", _mock_get)

        out_file = tmp_path / "testuser.jsonl"
        monkeypatch.setattr(
            sys, "argv",
            ["share_my_canvas.py", "--contributor", "testuser",
             "--output", str(out_file), "--dry-run"],
        )
        share_my_canvas.main()
        assert not out_file.exists(), "--dry-run must not write a file"

    def test_dry_run_stderr_has_records_and_checksum(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.setattr(share_my_canvas, "_get", _mock_get)

        out_file = tmp_path / "testuser.jsonl"
        monkeypatch.setattr(
            sys, "argv",
            ["share_my_canvas.py", "--contributor", "testuser",
             "--output", str(out_file), "--dry-run"],
        )
        share_my_canvas.main()
        captured = capsys.readouterr()
        assert "record" in captured.err.lower() or "record" in captured.out.lower(), \
            "dry-run output should mention record count"
        assert "sha256" in captured.err.lower() or "sha256" in captured.out.lower(), \
            "dry-run output should include sha256 checksum"

    def test_inspect_synonym(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CANVAS_TOKEN", "fake-token")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.setattr(share_my_canvas, "_get", _mock_get)

        out_file = tmp_path / "testuser.jsonl"
        monkeypatch.setattr(
            sys, "argv",
            ["share_my_canvas.py", "--contributor", "testuser",
             "--output", str(out_file), "--inspect"],
        )
        share_my_canvas.main()
        assert not out_file.exists(), "--inspect must not write a file"
