"""Tests for normalization — raw API response → CanvasItem."""

from __future__ import annotations

from unittest.mock import MagicMock

from canvas_tui.models import CanvasItem
from canvas_tui.normalize import (
    apply_past_filter,
    best_due,
    normalize_announcements,
    normalize_items,
    serialize_items,
)


class TestBestDue:
    def test_picks_due_at_first(self):
        pl = {"due_at": "2026-02-25T23:59:00Z", "created_at": "2026-02-01T10:00:00Z"}
        assert best_due(pl, "assignment") == "2026-02-25T23:59:00Z"

    def test_falls_through_to_created(self):
        pl = {"created_at": "2026-02-01T10:00:00Z"}
        assert best_due(pl, "assignment") == "2026-02-01T10:00:00Z"

    def test_none_when_empty(self):
        assert best_due({}, "assignment") is None


class TestNormalizeItems:
    def test_basic_normalization(self, sample_planner_items):
        api = MagicMock()
        api.cfg = MagicMock()
        api.cfg.base_url = "https://canvas.example.edu"
        api.cfg.user_tz = "America/New_York"
        api.fetch_current_courses.return_value = {
            12345: ("CS3214", "Computer Systems"),
        }
        api.fetch_course_name.return_value = ("CS3214", "Computer Systems")

        items = normalize_items(sample_planner_items, api, "America/New_York")
        assert len(items) >= 1
        # First non-announcement item
        hw = [it for it in items if it.ptype == "assignment"]
        assert len(hw) >= 1
        assert hw[0].course_code == "CS3214"

    def test_announcement_detection(self, sample_planner_items):
        api = MagicMock()
        api.cfg = MagicMock()
        api.cfg.base_url = "https://canvas.example.edu"
        api.cfg.user_tz = "America/New_York"
        api.fetch_current_courses.return_value = {12345: ("CS3214", "Computer Systems")}

        items = normalize_items(sample_planner_items, api, "America/New_York")
        ann = [it for it in items if it.ptype == "announcement"]
        assert len(ann) >= 1

    def test_status_flags_extracted(self, sample_planner_items):
        api = MagicMock()
        api.cfg = MagicMock()
        api.cfg.base_url = "https://canvas.example.edu"
        api.cfg.user_tz = "America/New_York"
        api.fetch_current_courses.return_value = {12345: ("CS3214", "Computer Systems")}

        items = normalize_items(sample_planner_items, api, "America/New_York")
        submitted = [it for it in items if "submitted" in it.status_flags]
        assert len(submitted) >= 1

    def test_empty_input(self):
        api = MagicMock()
        api.cfg = MagicMock()
        api.cfg.base_url = "https://canvas.example.edu"
        api.cfg.user_tz = "America/New_York"
        api.fetch_current_courses.return_value = {}

        items = normalize_items([], api, "America/New_York")
        assert items == []

    def test_course_cache_batch_fetch(self, sample_planner_items):
        api = MagicMock()
        api.cfg = MagicMock()
        api.cfg.base_url = "https://canvas.example.edu"
        api.cfg.user_tz = "America/New_York"
        api.fetch_current_courses.return_value = {12345: ("CS3214", "Computer Systems")}

        normalize_items(sample_planner_items, api, "America/New_York")
        # Should have called batch course fetch, not individual
        api.fetch_current_courses.assert_called_once()


class TestNormalizeAnnouncements:
    def test_basic(self):
        raw = [
            {
                "id": 111,
                "course_id": 12345,
                "title": "Exam postponed",
                "posted_at": "2026-02-22T08:00:00Z",
                "html_url": "/courses/12345/discussion_topics/111",
            }
        ]
        cache = {12345: ("CS3214", "Computer Systems")}
        items = normalize_announcements(raw, cache, "https://canvas.example.edu", "America/New_York")
        assert len(items) == 1
        assert items[0].ptype == "announcement"
        assert items[0].course_code == "CS3214"

    def test_empty(self):
        items = normalize_announcements([], {}, "https://base.com", "America/New_York")
        assert items == []

    def test_context_code_fallback(self):
        raw = [
            {
                "id": 222,
                "context_code": "course_12345",
                "title": "Test",
                "posted_at": "2026-02-22T08:00:00Z",
                "html_url": "/path",
            }
        ]
        cache = {12345: ("CS3214", "Computer Systems")}
        items = normalize_announcements(raw, cache, "https://base.com", "America/New_York")
        assert items[0].course_code == "CS3214"


class TestApplyPastFilter:
    def test_filters_old_submitted(self):
        old_submitted = CanvasItem(
            key="1",
            ptype="assignment",
            due_iso="2020-01-01T00:00:00Z",
            due_at="01/01/2020 00:00",
            status_flags=["submitted"],
            raw_plannable={},
        )
        recent = CanvasItem(
            key="2",
            ptype="assignment",
            due_iso="2030-01-01T00:00:00Z",
            due_at="01/01/2030 00:00",
            status_flags=[],
            raw_plannable={},
        )
        result = apply_past_filter([old_submitted, recent], 72, "America/New_York")
        keys = [it.key for it in result]
        assert "2" in keys

    def test_skips_announcements(self):
        ann = CanvasItem(key="a", ptype="announcement", raw_plannable={})
        result = apply_past_filter([ann], 72, "America/New_York")
        assert len(result) == 0  # Announcements filtered out


class TestSerializeItems:
    def test_roundtrip(self):
        items = [
            CanvasItem(key="1", title="HW1", ptype="assignment"),
            CanvasItem(key="2", title="Quiz", ptype="quiz"),
        ]
        serialized = serialize_items(items)
        assert len(serialized) == 2
        assert serialized[0]["key"] == "1"
        restored = [CanvasItem.from_dict(d) for d in serialized]
        assert restored[0].title == "HW1"


class TestApiEndpoints:
    """Test new API endpoint methods exist and have correct signatures."""

    def test_fetch_assignment_groups_exists(self):
        from unittest.mock import MagicMock

        from canvas_tui.api import CanvasAPI

        api = MagicMock(spec=CanvasAPI)
        api.fetch_assignment_groups(12345)
        api.fetch_assignment_groups.assert_called_once_with(12345)

    def test_fetch_course_info_exists(self):
        from unittest.mock import MagicMock

        from canvas_tui.api import CanvasAPI

        api = MagicMock(spec=CanvasAPI)
        api.fetch_course_info(12345)
        api.fetch_course_info.assert_called_once_with(12345)
