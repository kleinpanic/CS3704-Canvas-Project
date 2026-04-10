"""Tests for grades screen logic — calculate_grade_summary, sort_assignments."""

from __future__ import annotations

from canvas_tui.screens.grades import (
    GradeSummary,
    calculate_grade_summary,
    sort_assignments,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_assignment(
    name: str,
    points_possible: float | None = 100.0,
    score: float | None = None,
    workflow_state: str = "unsubmitted",
    submitted: bool = False,
    missing: bool = False,
    late: bool = False,
    excused: bool = False,
) -> dict:
    """Build a minimal Canvas assignment dict with an embedded submission."""
    sub: dict = {
        "workflow_state": "submitted" if submitted else workflow_state,
        "missing": missing,
        "late": late,
        "excused": excused,
    }
    if score is not None:
        sub["score"] = score
    return {
        "name": name,
        "points_possible": points_possible,
        "submission": sub,
    }


# ── calculate_grade_summary ───────────────────────────────────────────────────

class TestCalculateGradeSummary:
    def test_empty_assignments(self):
        result = calculate_grade_summary([], {})
        assert result.avg == 0.0
        assert result.projected_avg == 0.0
        assert result.graded == []
        assert result.ungraded == []
        assert not result.has_whatif

    def test_single_graded_assignment(self):
        assignments = [_make_assignment("HW1", score=90.0)]
        result = calculate_grade_summary(assignments, {})
        assert len(result.graded) == 1
        assert result.graded[0] == ("HW1", 90.0, 100.0)
        assert result.total_score == 90.0
        assert result.total_possible == 100.0
        assert result.avg == 90.0
        assert result.projected_avg == 90.0

    def test_manual_average_calculation(self):
        assignments = [
            _make_assignment("HW1", score=80.0),
            _make_assignment("HW2", score=90.0),
        ]
        result = calculate_grade_summary(assignments, {})
        assert result.total_score == 170.0
        assert result.total_possible == 200.0
        assert result.avg == 85.0

    def test_canvas_score_override(self):
        assignments = [_make_assignment("HW1", score=70.0)]
        result = calculate_grade_summary(assignments, {}, canvas_score_override=92.5)
        assert result.avg == 92.5
        # Manual total is still tracked for totals display
        assert result.total_score == 70.0

    def test_pending_assignment_goes_to_ungraded(self):
        assignments = [
            _make_assignment("HW1", score=85.0),
            _make_assignment("HW2"),  # unsubmitted, no score
        ]
        result = calculate_grade_summary(assignments, {})
        assert len(result.graded) == 1
        assert "HW2" in result.ungraded

    def test_submitted_ungraded_goes_to_ungraded(self):
        assignments = [_make_assignment("HW1", submitted=True)]
        result = calculate_grade_summary(assignments, {})
        assert "HW1" in result.ungraded

    def test_missing_assignment_not_in_ungraded(self):
        assignments = [_make_assignment("HW1", missing=True)]
        result = calculate_grade_summary(assignments, {})
        assert "HW1" not in result.ungraded
        assert result.graded == []

    def test_excused_assignment_skipped_entirely(self):
        assignments = [_make_assignment("HW1", excused=True, score=None)]
        result = calculate_grade_summary(assignments, {})
        assert result.graded == []
        assert result.ungraded == []
        assert result.total_possible == 0.0

    def test_whatif_sets_has_whatif_flag(self):
        assignments = [_make_assignment("HW1")]
        result = calculate_grade_summary(assignments, {"HW1": 75.0})
        assert result.has_whatif

    def test_whatif_contributes_to_projected_avg(self):
        assignments = [
            _make_assignment("HW1", score=100.0),
            _make_assignment("HW2"),  # no score → what-if
        ]
        whatif = {"HW2": 80.0}
        result = calculate_grade_summary(assignments, whatif)
        # projected = (100 + 80) / 200 = 90%
        assert result.projected_avg == 90.0
        # actual avg = 100/100 = 100%
        assert result.avg == 100.0

    def test_whatif_does_not_affect_actual_avg(self):
        assignments = [_make_assignment("HW1")]
        result = calculate_grade_summary(assignments, {"HW1": 50.0})
        # No real grades, so avg is 0 (or override)
        assert result.avg == 0.0

    def test_whatif_projected_when_no_real_grades(self):
        assignments = [_make_assignment("HW1", points_possible=100.0)]
        result = calculate_grade_summary(assignments, {"HW1": 70.0})
        assert result.projected_avg == 70.0

    def test_whatif_ignored_for_already_graded_assignment(self):
        # Canvas API returns a real score; what-if should not override the real score
        assignments = [_make_assignment("HW1", score=90.0)]
        result = calculate_grade_summary(assignments, {"HW1": 50.0})
        # Real grade (90) still goes through graded path; what-if does not replace it
        assert result.total_score == 90.0

    def test_multiple_whatif_scores(self):
        assignments = [
            _make_assignment("HW1", score=80.0),
            _make_assignment("HW2"),
            _make_assignment("HW3"),
        ]
        whatif = {"HW2": 90.0, "HW3": 70.0}
        result = calculate_grade_summary(assignments, whatif)
        # projected = (80 + 90 + 70) / 300
        assert abs(result.projected_avg - 80.0) < 0.01

    def test_zero_points_possible_excluded_from_totals(self):
        assignments = [_make_assignment("Extra", points_possible=0.0, score=5.0)]
        result = calculate_grade_summary(assignments, {})
        # points_possible=0 → skipped from total_score/total_possible
        assert result.total_possible == 0.0

    def test_none_points_possible_excluded_from_totals(self):
        assignments = [_make_assignment("Survey", points_possible=None, score=1.0)]
        result = calculate_grade_summary(assignments, {})
        assert result.total_possible == 0.0


# ── sort_assignments ──────────────────────────────────────────────────────────

class TestSortAssignments:
    def _sample(self) -> list[dict]:
        return [
            _make_assignment("Beta", score=70.0, points_possible=100.0),
            _make_assignment("Alpha", score=90.0, points_possible=100.0),
            _make_assignment("Gamma"),  # no score
        ]

    def test_mode_0_preserves_order(self):
        assignments = self._sample()
        result = sort_assignments(assignments, 0)
        assert [a["name"] for a in result] == ["Beta", "Alpha", "Gamma"]

    def test_mode_1_sorts_by_score_desc(self):
        assignments = self._sample()
        result = sort_assignments(assignments, 1)
        names = [a["name"] for a in result]
        assert names[0] == "Alpha"  # 90 highest
        assert names[1] == "Beta"   # 70 second

    def test_mode_1_ungraded_to_end(self):
        assignments = self._sample()
        result = sort_assignments(assignments, 1)
        assert result[-1]["name"] == "Gamma"

    def test_mode_2_sorts_by_pct_desc(self):
        assignments = [
            _make_assignment("A", score=50.0, points_possible=100.0),  # 50%
            _make_assignment("B", score=8.0, points_possible=10.0),    # 80%
        ]
        result = sort_assignments(assignments, 2)
        assert result[0]["name"] == "B"

    def test_mode_2_ungraded_to_end(self):
        assignments = self._sample()
        result = sort_assignments(assignments, 2)
        assert result[-1]["name"] == "Gamma"

    def test_mode_3_sorts_by_name_alpha(self):
        assignments = self._sample()
        result = sort_assignments(assignments, 3)
        assert result[0]["name"] == "Alpha"
        assert result[1]["name"] == "Beta"
        assert result[2]["name"] == "Gamma"

    def test_mode_3_case_insensitive(self):
        assignments = [
            _make_assignment("zebra"),
            _make_assignment("Apple"),
        ]
        result = sort_assignments(assignments, 3)
        assert result[0]["name"] == "Apple"

    def test_does_not_mutate_original(self):
        assignments = self._sample()
        original_order = [a["name"] for a in assignments]
        sort_assignments(assignments, 3)
        assert [a["name"] for a in assignments] == original_order

    def test_unknown_mode_returns_copy(self):
        assignments = self._sample()
        result = sort_assignments(assignments, 99)
        assert [a["name"] for a in result] == [a["name"] for a in assignments]

    def test_empty_list(self):
        assert sort_assignments([], 1) == []


# ── GradeSummary dataclass ────────────────────────────────────────────────────

class TestGradeSummary:
    def test_defaults(self):
        s = GradeSummary(avg=85.0, projected_avg=88.0, total_score=850.0, total_possible=1000.0)
        assert s.graded == []
        assert s.ungraded == []
        assert not s.has_whatif

    def test_fields(self):
        s = GradeSummary(
            avg=90.0,
            projected_avg=92.0,
            total_score=900.0,
            total_possible=1000.0,
            graded=[("HW1", 90.0, 100.0)],
            ungraded=["HW2"],
            has_whatif=True,
        )
        assert s.avg == 90.0
        assert s.projected_avg == 92.0
        assert len(s.graded) == 1
        assert s.ungraded == ["HW2"]
        assert s.has_whatif
