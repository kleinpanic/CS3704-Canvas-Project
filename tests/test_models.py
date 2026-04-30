"""Tests for data models."""

from __future__ import annotations

from canvas_tui.models import CanvasItem, CourseInfo, ModalContext


class TestCanvasItem:
    def test_defaults(self):
        item = CanvasItem()
        assert item.key == ""
        assert item.title == "(untitled)"
        assert item.points is None
        assert item.status_flags == []

    def test_to_dict_roundtrip(self):
        item = CanvasItem(
            key="123:456:assignment",
            ptype="assignment",
            title="HW3",
            course_code="CS3214",
            points=100.0,
            status_flags=["submitted"],
        )
        d = item.to_dict()
        restored = CanvasItem.from_dict(d)
        assert restored.key == item.key
        assert restored.title == item.title
        assert restored.points == item.points
        assert restored.status_flags == item.status_flags

    def test_from_dict_handles_missing_keys(self):
        item = CanvasItem.from_dict({})
        assert item.key == ""
        assert item.title == "(untitled)"

    def test_due_iso_to_dict_roundtrip(self):
        item = CanvasItem(
            key="123:456:assignment",
            ptype="assignment",
            title="HW Due Soon",
            course_code="CS3214",
            points=100.0,
            due_iso="2026-04-24T23:59:00Z",
            status_flags=[],
        )

        d = item.to_dict()
        restored = CanvasItem.from_dict(d)

        assert restored.due_iso == item.due_iso
        assert restored.title == item.title
        assert restored.course_code == item.course_code
        assert restored.ptype == item.ptype


class TestCourseInfo:
    def test_defaults(self):
        c = CourseInfo()
        assert c.course_id == 0
        assert c.course_code == ""


class TestModalContext:
    def test_unique_ids(self):
        m1 = ModalContext(kind="test")
        m2 = ModalContext(kind="test")
        assert m1.modal_id != m2.modal_id
