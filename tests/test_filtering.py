"""Tests for filtering and fuzzy search."""

from __future__ import annotations

from canvas_tui.filtering import FilterQuery, filter_items, format_filter_summary, fuzzy_score
from canvas_tui.models import CanvasItem


class TestFilterQueryParse:
    def test_empty(self):
        q = FilterQuery.parse("")
        assert q.is_empty

    def test_course_prefix(self):
        q = FilterQuery.parse("course:CS3214")
        assert q.course == ["cs3214"]
        assert q.is_empty is False

    def test_type_prefix(self):
        q = FilterQuery.parse("type:assignment")
        assert q.ptype == ["assignment"]

    def test_status_prefix(self):
        q = FilterQuery.parse("status:graded")
        assert q.status == ["graded"]

    def test_has_prefix(self):
        q = FilterQuery.parse("has:points")
        assert q.has == ["points"]

    def test_free_text(self):
        q = FilterQuery.parse("homework structures")
        assert q.text == ["homework", "structures"]

    def test_mixed(self):
        q = FilterQuery.parse("course:CS3214 type:assignment homework")
        assert q.course == ["cs3214"]
        assert q.ptype == ["assignment"]
        assert q.text == ["homework"]

    def test_short_prefixes(self):
        q = FilterQuery.parse("c:CS3214 t:quiz s:graded")
        assert q.course == ["cs3214"]
        assert q.ptype == ["quiz"]
        assert q.status == ["graded"]


class TestFuzzyScore:
    def test_exact_match(self):
        assert fuzzy_score("homework", "Homework 3: Data Structures") > 0.8

    def test_prefix_match(self):
        assert fuzzy_score("hw", "hw3-data-structures") > 0.5

    def test_subsequence(self):
        assert fuzzy_score("hds", "Homework Data Structures") > 0.0

    def test_no_match(self):
        assert fuzzy_score("xyz123", "Homework 3") == 0.0

    def test_empty_needle(self):
        assert fuzzy_score("", "anything") == 1.0


class TestFilterItems:
    def _make_items(self) -> list[CanvasItem]:
        return [
            CanvasItem(
                key="1",
                title="Homework 3: Data Structures",
                course_code="CS3214",
                ptype="assignment",
                points=100.0,
                status_flags=[],
            ),
            CanvasItem(
                key="2",
                title="Quiz 2: Algorithms",
                course_code="CS4104",
                ptype="quiz",
                points=50.0,
                status_flags=["graded"],
            ),
            CanvasItem(
                key="3",
                title="Lab Report",
                course_code="CS3214",
                ptype="assignment",
                points=None,
                status_flags=["submitted"],
            ),
            CanvasItem(
                key="4", title="Final Exam", course_code="CS4104", ptype="assignment", points=200.0, status_flags=[]
            ),
        ]

    def test_course_filter(self):
        items = self._make_items()
        q = FilterQuery.parse("course:CS3214")
        result = filter_items(items, q)
        assert len(result) == 2
        assert all(items[i].course_code == "CS3214" for i in result)

    def test_type_filter(self):
        items = self._make_items()
        q = FilterQuery.parse("type:quiz")
        result = filter_items(items, q)
        assert len(result) == 1
        assert items[result[0]].ptype == "quiz"

    def test_status_filter(self):
        items = self._make_items()
        q = FilterQuery.parse("status:graded")
        result = filter_items(items, q)
        assert len(result) == 1

    def test_has_points(self):
        items = self._make_items()
        q = FilterQuery.parse("has:points")
        result = filter_items(items, q)
        # Items 0, 1, 3 have points > 0
        assert len(result) == 3

    def test_free_text(self):
        items = self._make_items()
        q = FilterQuery.parse("homework")
        result = filter_items(items, q)
        assert len(result) >= 1
        assert items[result[0]].title.startswith("Homework")

    def test_combined_filter(self):
        items = self._make_items()
        q = FilterQuery.parse("course:CS4104 type:assignment")
        result = filter_items(items, q)
        assert len(result) == 1
        assert items[result[0]].title == "Final Exam"

    def test_empty_filter_returns_all(self):
        items = self._make_items()
        q = FilterQuery.parse("")
        result = filter_items(items, q)
        assert len(result) == len(items)

    def test_course_filter_no_matches(self):
        items = self._make_items()
        q = FilterQuery.parse("course:MATH9999")

        result = filter_items(items, q)

        assert result == []

    def test_combined_filter_no_matches(self):
        items = self._make_items()
        q = FilterQuery.parse("course:CS3214 type:quiz")

        result = filter_items(items, q)

        assert result == []

    def test_course_filter_is_case_insensitive(self):
        items = self._make_items()
        q = FilterQuery.parse("course:cs3214")

        result = filter_items(items, q)

        assert len(result) == 2
        assert all(items[i].course_code == "CS3214" for i in result)

    def test_integration_parse_filter_and_fuzzy_text(self):
        items = self._make_items()
        q = FilterQuery.parse("course:CS4104 type:assignment final")

        result = filter_items(items, q)

        assert len(result) == 1
        matched = items[result[0]]
        assert matched.title == "Final Exam"
        assert matched.course_code == "CS4104"
        assert matched.ptype == "assignment"

    def test_course_filter_no_matches(self):
        items = self._make_items()
        q = FilterQuery.parse("course:MATH9999")

        result = filter_items(items, q)

        assert result == []

    def test_combined_filter_no_matches(self):
        items = self._make_items()
        q = FilterQuery.parse("course:CS3214 type:quiz")

        result = filter_items(items, q)

        assert result == []

    def test_course_filter_is_case_insensitive(self):
        items = self._make_items()
        q = FilterQuery.parse("course:cs3214")

        result = filter_items(items, q)

        assert len(result) == 2
        assert all(items[i].course_code == "CS3214" for i in result)

    def test_integration_parse_filter_and_fuzzy_text(self):
        items = self._make_items()
        q = FilterQuery.parse("course:CS4104 type:assignment final")

        result = filter_items(items, q)

        assert len(result) == 1
        matched = items[result[0]]
        assert matched.title == "Final Exam"
        assert matched.course_code == "CS4104"
        assert matched.ptype == "assignment"


class TestFormatFilterSummary:
    def test_basic(self):
        q = FilterQuery.parse("course:CS3214 homework")
        s = format_filter_summary(q, 2, 10)
        assert "cs3214" in s.lower()
        assert "2/10" in s
