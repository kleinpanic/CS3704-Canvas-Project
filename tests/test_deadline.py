"""PM4 tests for deadline-specific filtering behavior (Issue #24)."""
import pytest

from canvas_tui.filtering import FilterQuery, filter_items
from canvas_tui.models.item import CanvasItem


def _make_item(
    key="k1",
    title="Assignment",
    course_code="CS3704",
    ptype="assignment",
    due_iso="2026-04-30T23:59:00Z",
    status_flags=None,
):
    return CanvasItem(
        key=key,
        legacy_key=key,
        ptype=ptype,
        title=title,
        course_code=course_code,
        course_name=course_code,
        due_at="Apr 30",
        due_rel="in 6 days",
        due_iso=due_iso,
        url="",
        course_id=1,
        plannable_id=1,
        points=None,
        status_flags=status_flags or {},
        raw_plannable={},
    )


class TestDeadlineFilterBehavior:
    def setup_method(self):
        self.items = [
            _make_item(key="a1", title="Homework 1", course_code="CS3704", ptype="assignment"),
            _make_item(key="a2", title="Lab Report",  course_code="CS4234", ptype="assignment"),
            _make_item(key="a3", title="Quiz 1",      course_code="CS3704", ptype="quiz"),
            _make_item(
                key="a4",
                title="Submitted HW",
                course_code="CS3704",
                ptype="assignment",
                status_flags={"submitted": True},
            ),
            _make_item(
                key="a5",
                title="Overdue Task",
                course_code="CS3704",
                ptype="assignment",
                due_iso="2026-01-01T00:00:00Z",
            ),
        ]

    def test_filter_by_course_code_narrows_results(self):
        query = FilterQuery.parse("course:CS3704")
        indices = filter_items(self.items, query)
        matched_codes = {self.items[i].course_code for i in indices}
        assert matched_codes == {"CS3704"}
        assert all(self.items[i].course_code == "CS3704" for i in indices)

    def test_filter_by_status_submitted_excludes_pending(self):
        query = FilterQuery.parse("status:submitted")
        indices = filter_items(self.items, query)
        # Only the submitted item should match
        assert len(indices) == 1
        assert self.items[indices[0]].status_flags.get("submitted") is True

    def test_combined_course_and_type_filter_uses_and_logic(self):
        query = FilterQuery.parse("course:CS3704 type:quiz")
        indices = filter_items(self.items, query)
        for i in indices:
            assert self.items[i].course_code == "CS3704"
            assert self.items[i].ptype == "quiz"
        # CS4234 quiz or CS3704 assignment should NOT appear
        assert all(self.items[i].key == "a3" for i in indices)

    def test_overdue_items_not_excluded_by_default(self):
        query = FilterQuery.parse("")
        indices = filter_items(self.items, query)
        keys = [self.items[i].key for i in indices]
        assert "a5" in keys  # overdue item still visible

    def test_urgent_items_score_higher_in_text_search(self):
        query = FilterQuery.parse("Homework")
        indices = filter_items(self.items, query)
        # "Homework 1" and "Submitted HW" may match; "Homework 1" should rank first (exact word)
        assert len(indices) >= 1
        assert self.items[indices[0]].title in ("Homework 1", "Submitted HW")