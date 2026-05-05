"""Unit tests for canvas_sdk.host.__main__

Tests cover:
  - _serialize with a mock CanvasObject
  - _drain limits output to 100 items
  - _handle returns error when no token
  - _handle returns error for unknown method
"""

import pytest
from unittest.mock import MagicMock, patch

# Import the module under test
from canvas_sdk.host.__main__ import _serialize, _drain, _handle


# ── Helpers ───────────────────────────────────────────────────────────────────

class FakeCanvasObject:
    """Minimal stand-in for a CanvasObject with instance variables."""

    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)


# ── _serialize tests ──────────────────────────────────────────────────────────

class TestSerialize:
    def test_primitives_pass_through(self):
        assert _serialize(None) is None
        assert _serialize(42) == 42
        assert _serialize(3.14) == 3.14
        assert _serialize(True) is True
        assert _serialize("hello") == "hello"

    def test_dict_is_recursed(self):
        result = _serialize({"a": 1, "b": "x"})
        assert result == {"a": 1, "b": "x"}

    def test_list_is_recursed(self):
        result = _serialize([1, "two", None])
        assert result == [1, "two", None]

    def test_canvas_object_uses_vars(self):
        obj = FakeCanvasObject(id=99, name="Test Course", course_code="CS101")
        result = _serialize(obj)
        assert result == {"id": 99, "name": "Test Course", "course_code": "CS101"}

    def test_private_keys_are_excluded(self):
        obj = FakeCanvasObject(id=1, _requester=object(), name="visible")
        result = _serialize(obj)
        assert "_requester" not in result
        assert result["id"] == 1
        assert result["name"] == "visible"

    def test_date_keys_are_excluded(self):
        obj = FakeCanvasObject(id=2, created_at_date="2024-01-01", name="keep")
        result = _serialize(obj)
        assert "created_at_date" not in result
        assert result["name"] == "keep"

    def test_nested_canvas_object(self):
        inner = FakeCanvasObject(x=5)
        outer = FakeCanvasObject(id=1, nested=inner)
        result = _serialize(outer)
        assert result["nested"] == {"x": 5}

    def test_unknown_type_converted_to_str(self):
        class Weird:
            def __str__(self):
                return "weird-string"

        # Weird has no __dict__-based attrs we want, but it does have __dict__
        # via Python's default instance dict.  The serializer will use vars().
        # An object with no interesting attributes should serialize to {}.
        obj = Weird()
        result = _serialize(obj)
        # It has a __dict__ (empty), so we get {}
        assert isinstance(result, dict)


# ── _drain tests ──────────────────────────────────────────────────────────────

class TestDrain:
    def _make_paginated(self, n):
        """Return a plain list of FakeCanvasObjects (iterator compatible)."""
        return [FakeCanvasObject(id=i) for i in range(n)]

    def test_drain_returns_all_items_when_under_limit(self):
        items = self._make_paginated(10)
        result = _drain(items, limit=100)
        assert len(result) == 10

    def test_drain_caps_at_limit(self):
        items = self._make_paginated(200)
        result = _drain(items, limit=100)
        assert len(result) == 100

    def test_drain_default_limit_is_100(self):
        items = self._make_paginated(150)
        result = _drain(items)
        assert len(result) == 100

    def test_drain_serializes_items(self):
        items = [FakeCanvasObject(id=7, name="course")]
        result = _drain(items, limit=100)
        assert result == [{"id": 7, "name": "course"}]

    def test_drain_empty_list(self):
        result = _drain([], limit=100)
        assert result == []

    def test_drain_exact_limit(self):
        items = self._make_paginated(100)
        result = _drain(items, limit=100)
        assert len(result) == 100


# ── _handle tests ─────────────────────────────────────────────────────────────

class TestHandle:
    def test_no_token_returns_error(self):
        msg = {"method": "getCourses", "baseUrl": "https://canvas.vt.edu"}
        result = _handle(msg)
        assert result["ok"] is False
        assert "token" in result["error"].lower() or result["error"] == "No token"

    def test_unknown_method_returns_error(self):
        mock_canvas = MagicMock()
        mock_canvas.get_current_user.return_value = FakeCanvasObject(id=1, name="User")

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "notARealMethod", "token": "fake-token"}
            result = _handle(msg)

        assert result["ok"] is False
        assert "notARealMethod" in result["error"]

    def test_get_user_method(self):
        mock_user = FakeCanvasObject(id=42, name="Alice")
        mock_canvas = MagicMock()
        mock_canvas.get_current_user.return_value = mock_user

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "getUser", "token": "fake-token"}
            result = _handle(msg)

        assert result["ok"] is True
        assert result["data"]["id"] == 42

    def test_validate_token_method(self):
        mock_user = FakeCanvasObject(id=99, name="Bob")
        mock_canvas = MagicMock()
        mock_canvas.get_current_user.return_value = mock_user

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "validateToken", "token": "fake-token"}
            result = _handle(msg)

        assert result["ok"] is True
        assert result["user"]["id"] == 99

    def test_get_courses_method(self):
        mock_courses = [FakeCanvasObject(id=1, name="Math"), FakeCanvasObject(id=2, name="CS")]
        mock_canvas = MagicMock()
        mock_canvas.get_courses.return_value = mock_courses

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "getCourses", "token": "fake-token"}
            result = _handle(msg)

        assert result["ok"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["name"] == "Math"

    def test_get_todo_method(self):
        mock_todos = [FakeCanvasObject(id=10, type="submitting")]
        mock_canvas = MagicMock()
        mock_canvas.get_todo_items.return_value = mock_todos

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "getTodo", "token": "fake-token"}
            result = _handle(msg)

        assert result["ok"] is True
        assert len(result["data"]) == 1

    def test_get_planner_notes_method(self):
        mock_notes = [FakeCanvasObject(id=5, title="Study")]
        mock_canvas = MagicMock()
        mock_canvas.get_planner_notes.return_value = mock_notes

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "getPlannerNotes", "token": "fake-token"}
            result = _handle(msg)

        assert result["ok"] is True
        assert result["data"][0]["title"] == "Study"

    def test_course_method_missing_course_id_returns_error(self):
        mock_canvas = MagicMock()

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "getCourseAssignments", "token": "fake-token", "params": {}}
            result = _handle(msg)

        assert result["ok"] is False
        assert "courseId" in result["error"]

    def test_get_course_assignments_method(self):
        mock_assignment = FakeCanvasObject(id=1, name="HW1")
        mock_course = MagicMock()
        mock_course.get_assignments.return_value = [mock_assignment]
        mock_canvas = MagicMock()
        mock_canvas.get_course.return_value = mock_course

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {
                "method": "getCourseAssignments",
                "token": "fake-token",
                "params": {"courseId": 123},
            }
            result = _handle(msg)

        assert result["ok"] is True
        assert result["data"][0]["name"] == "HW1"

    def test_get_course_grades_method(self):
        mock_enrollment = FakeCanvasObject(id=1, current_score=95.0)
        mock_course = MagicMock()
        mock_course.get_enrollments.return_value = [mock_enrollment]
        mock_canvas = MagicMock()
        mock_canvas.get_course.return_value = mock_course

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {
                "method": "getCourseGrades",
                "token": "fake-token",
                "params": {"courseId": 456},
            }
            result = _handle(msg)

        assert result["ok"] is True
        assert result["data"][0]["current_score"] == 95.0

    def test_get_course_announcements_method(self):
        mock_topic = FakeCanvasObject(id=1, title="Announcement 1")
        mock_course = MagicMock()
        mock_course.get_discussion_topics.return_value = [mock_topic]
        mock_canvas = MagicMock()
        mock_canvas.get_course.return_value = mock_course

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {
                "method": "getCourseAnnouncements",
                "token": "fake-token",
                "params": {"courseId": 789},
            }
            result = _handle(msg)

        assert result["ok"] is True
        assert result["data"][0]["title"] == "Announcement 1"

    def test_get_course_modules_method(self):
        mock_module = FakeCanvasObject(id=1, name="Week 1")
        mock_course = MagicMock()
        mock_course.get_modules.return_value = [mock_module]
        mock_canvas = MagicMock()
        mock_canvas.get_course.return_value = mock_course

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {
                "method": "getCourseModules",
                "token": "fake-token",
                "params": {"courseId": 101},
            }
            result = _handle(msg)

        assert result["ok"] is True
        assert result["data"][0]["name"] == "Week 1"

    def test_get_course_files_method(self):
        mock_file = FakeCanvasObject(id=1, display_name="syllabus.pdf")
        mock_course = MagicMock()
        mock_course.get_files.return_value = [mock_file]
        mock_canvas = MagicMock()
        mock_canvas.get_course.return_value = mock_course

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {
                "method": "getCourseFiles",
                "token": "fake-token",
                "params": {"courseId": 202},
            }
            result = _handle(msg)

        assert result["ok"] is True
        assert result["data"][0]["display_name"] == "syllabus.pdf"

    def test_get_upcoming_assignments_method(self):
        mock_canvas = MagicMock()
        # get_upcoming_events returns a plain list (not PaginatedList)
        mock_canvas.get_upcoming_events.return_value = [{"id": 1, "title": "Quiz"}]

        with patch("canvas_sdk.host.__main__.Canvas", return_value=mock_canvas):
            msg = {"method": "getUpcomingAssignments", "token": "fake-token"}
            result = _handle(msg)

        assert result["ok"] is True
        assert len(result["data"]) == 1
