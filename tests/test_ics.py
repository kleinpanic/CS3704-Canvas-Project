"""Tests for ICS export."""

from __future__ import annotations

import os

from canvas_tui.config import Config
from canvas_tui.ics import export_ics, ics_escape, item_to_vevent
from canvas_tui.models import CanvasItem


class TestIcsEscape:
    def test_semicolons(self):
        assert "\\;" in ics_escape("test;value")

    def test_commas(self):
        assert "\\," in ics_escape("test,value")

    def test_newlines(self):
        assert "\\n" in ics_escape("line1\nline2")

    def test_backslash(self):
        assert "\\\\" in ics_escape("path\\to\\file")


class TestItemToVevent:
    def test_basic_event(self):
        cfg = Config(token="test", user_tz="America/New_York")
        item = CanvasItem(
            key="123:456:assignment",
            ptype="assignment",
            title="Homework 3",
            course_code="CS3214",
            course_name="Computer Systems",
            due_iso="2026-02-25T23:59:00Z",
            url="https://canvas.vt.edu/courses/123/assignments/456",
        )
        result = item_to_vevent(item, cfg)
        assert result is not None
        assert "BEGIN:VEVENT" in result
        assert "END:VEVENT" in result
        assert "CS3214" in result
        assert "Homework 3" in result

    def test_no_due_date_returns_none(self):
        cfg = Config(token="test")
        item = CanvasItem(key="1", due_iso="")
        assert item_to_vevent(item, cfg) is None


class TestExportIcs:
    def test_exports_file(self, tmp_dir):
        cfg = Config(token="test", export_dir=tmp_dir)
        items = [
            CanvasItem(
                key="1",
                ptype="assignment",
                title="HW1",
                course_code="CS101",
                due_iso="2026-02-25T23:59:00Z",
                url="https://example.com",
            ),
            CanvasItem(key="2", ptype="quiz", title="Quiz 1", due_iso=""),
        ]
        path = export_ics(items, cfg, os.path.join(tmp_dir, "test.ics"))
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "BEGIN:VCALENDAR" in content
        assert "BEGIN:VEVENT" in content
        assert "CS101" in content
        assert "HW1" in content

    def test_empty_items(self, tmp_dir):
        cfg = Config(token="test", export_dir=tmp_dir)
        path = export_ics([], cfg, os.path.join(tmp_dir, "empty.ics"))
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "BEGIN:VCALENDAR" in content
        assert "VEVENT" not in content
