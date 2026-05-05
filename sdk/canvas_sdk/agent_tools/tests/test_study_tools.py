import datetime as dt
import pytest

from canvas_sdk.agent_tools.study_tools import (
    SpacedSchedule,
    SemesterSchedule,
    DeepBlockSize,
    ExamBracket,
)


# ---------------------------------------------------------------------------
# SpacedSchedule
# ---------------------------------------------------------------------------

def test_spaced_schedule_returns_n_sessions(exam_iso):
    result = SpacedSchedule.call({"exam_iso": exam_iso, "n_sessions": 3})
    assert len(result) == 3


def test_spaced_schedule_all_sessions_before_exam(exam_iso):
    exam_dt = dt.datetime(2026, 5, 22, 14, 0, 0, tzinfo=dt.timezone.utc)
    result = SpacedSchedule.call({"exam_iso": exam_iso, "n_sessions": 3})
    for session in result:
        start = dt.datetime.fromisoformat(session["start_iso"])
        assert start < exam_dt, f"Session {session['start_iso']} is not before exam {exam_iso}"


def test_spaced_schedule_labels_contain_before(exam_iso):
    result = SpacedSchedule.call({"exam_iso": exam_iso, "n_sessions": 3})
    for session in result:
        assert "before" in session["label"].lower(), f"Label missing 'before': {session['label']!r}"


def test_spaced_schedule_session_fields(exam_iso):
    result = SpacedSchedule.call({"exam_iso": exam_iso, "n_sessions": 4})
    for session in result:
        assert "start_iso" in session
        assert "end_iso" in session
        assert "label" in session
        assert "minutes" in session


def test_spaced_schedule_clamp_below_3():
    exam = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=20)).isoformat()
    result = SpacedSchedule.call({"exam_iso": exam, "n_sessions": 1})
    assert len(result) == 3


def test_spaced_schedule_clamp_above_5():
    exam = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=20)).isoformat()
    result = SpacedSchedule.call({"exam_iso": exam, "n_sessions": 8})
    assert len(result) == 5


def test_spaced_schedule_default_4_sessions(exam_iso):
    result = SpacedSchedule.call({"exam_iso": exam_iso})
    assert len(result) == 4


def test_spaced_schedule_end_after_start(exam_iso):
    result = SpacedSchedule.call({"exam_iso": exam_iso, "n_sessions": 3})
    for session in result:
        start = dt.datetime.fromisoformat(session["start_iso"])
        end = dt.datetime.fromisoformat(session["end_iso"])
        assert end > start


# ---------------------------------------------------------------------------
# SemesterSchedule
# ---------------------------------------------------------------------------

def _future_iso(days):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days)).isoformat()


def test_semester_schedule_returns_2_entries_for_2_deadlines():
    deadlines = [
        {"title": "Milestone A", "due_iso": _future_iso(30), "estimated_hours": 20},
        {"title": "Milestone B", "due_iso": _future_iso(60), "estimated_hours": 30},
    ]
    result = SemesterSchedule.call({
        "semester_end_iso": _future_iso(90),
        "deadlines": deadlines,
    })
    assert len(result) == 2


def test_semester_schedule_entry_has_required_fields():
    deadlines = [
        {"title": "Final Project", "due_iso": _future_iso(40), "estimated_hours": 25},
    ]
    result = SemesterSchedule.call({
        "semester_end_iso": _future_iso(80),
        "deadlines": deadlines,
    })
    entry = result[0]
    assert "milestone" in entry
    assert "due_iso" in entry
    assert "start_work_iso" in entry
    assert "recommended_hours_per_week" in entry
    assert "intensity" in entry


def test_semester_schedule_milestone_matches_title():
    deadlines = [
        {"title": "Report Draft", "due_iso": _future_iso(35), "estimated_hours": 10},
    ]
    result = SemesterSchedule.call({
        "semester_end_iso": _future_iso(70),
        "deadlines": deadlines,
    })
    assert result[0]["milestone"] == "Report Draft"


def test_semester_schedule_due_iso_preserved():
    due = _future_iso(30)
    deadlines = [{"title": "X", "due_iso": due, "estimated_hours": 10}]
    result = SemesterSchedule.call({
        "semester_end_iso": _future_iso(60),
        "deadlines": deadlines,
    })
    assert result[0]["due_iso"] == due


def test_semester_schedule_high_intensity_near_deadline():
    # deadline is 5 days away; semester end is 100 days away
    # ramp_cutoff = 100 * 0.75 = 75; days_left=5 < 75 → "high"
    deadlines = [
        {"title": "Urgent", "due_iso": _future_iso(5), "estimated_hours": 15},
    ]
    result = SemesterSchedule.call({
        "semester_end_iso": _future_iso(100),
        "deadlines": deadlines,
    })
    assert result[0]["intensity"] == "high"


def test_semester_schedule_normal_intensity_far_from_deadline():
    # deadline 80 days away; semester end 100 days — ramp_cutoff=75; days_left=80 > 75 → "normal"
    deadlines = [
        {"title": "Distant", "due_iso": _future_iso(80), "estimated_hours": 15},
    ]
    result = SemesterSchedule.call({
        "semester_end_iso": _future_iso(100),
        "deadlines": deadlines,
    })
    assert result[0]["intensity"] == "normal"


def test_semester_schedule_recommended_hours_per_week_positive():
    deadlines = [{"title": "X", "due_iso": _future_iso(30), "estimated_hours": 20}]
    result = SemesterSchedule.call({
        "semester_end_iso": _future_iso(60),
        "deadlines": deadlines,
        "weekly_hours_available": 8,
    })
    assert result[0]["recommended_hours_per_week"] > 0


# ---------------------------------------------------------------------------
# DeepBlockSize
# ---------------------------------------------------------------------------

def test_deep_block_size_writing():
    result = DeepBlockSize.call({"task_type": "writing"})
    assert result["minutes"] == 90
    assert "rationale" in result
    assert len(result["rationale"]) > 0


def test_deep_block_size_lab():
    result = DeepBlockSize.call({"task_type": "lab"})
    assert result["minutes"] == 120
    assert "rationale" in result


def test_deep_block_size_problem_set():
    result = DeepBlockSize.call({"task_type": "problem_set"})
    assert result["minutes"] == 90


def test_deep_block_size_admin():
    result = DeepBlockSize.call({"task_type": "admin"})
    assert result["minutes"] == 25


def test_deep_block_size_reading():
    result = DeepBlockSize.call({"task_type": "reading"})
    assert result["minutes"] == 45


def test_deep_block_size_unknown_raises_key_error():
    with pytest.raises(KeyError):
        DeepBlockSize.call({"task_type": "underwater_basket_weaving"})


def test_deep_block_size_returns_minutes_and_rationale():
    result = DeepBlockSize.call({"task_type": "review"})
    assert set(result.keys()) == {"minutes", "rationale"}


# ---------------------------------------------------------------------------
# ExamBracket
# ---------------------------------------------------------------------------

def test_exam_bracket_returns_2_blocks():
    result = ExamBracket.call({
        "exam_start_iso": "2026-05-22T14:00:00+00:00",
        "exam_end_iso": "2026-05-22T16:00:00+00:00",
    })
    assert len(result) == 2


def test_exam_bracket_first_block_ends_15min_before_exam():
    exam_start = dt.datetime(2026, 5, 22, 14, 0, 0, tzinfo=dt.timezone.utc)
    result = ExamBracket.call({
        "exam_start_iso": "2026-05-22T14:00:00+00:00",
        "exam_end_iso": "2026-05-22T16:00:00+00:00",
    })
    first_end = dt.datetime.fromisoformat(result[0]["end_iso"])
    expected_end = exam_start - dt.timedelta(minutes=15)
    assert first_end == expected_end


def test_exam_bracket_second_block_starts_at_exam_end():
    exam_end = dt.datetime(2026, 5, 22, 16, 0, 0, tzinfo=dt.timezone.utc)
    result = ExamBracket.call({
        "exam_start_iso": "2026-05-22T14:00:00+00:00",
        "exam_end_iso": "2026-05-22T16:00:00+00:00",
    })
    second_start = dt.datetime.fromisoformat(result[1]["start_iso"])
    assert second_start == exam_end


def test_exam_bracket_has_label_fields():
    result = ExamBracket.call({
        "exam_start_iso": "2026-05-22T14:00:00+00:00",
        "exam_end_iso": "2026-05-22T16:00:00+00:00",
    })
    for block in result:
        assert "label" in block
        assert "start_iso" in block
        assert "end_iso" in block


def test_exam_bracket_first_block_review_duration():
    # default review_minutes=45; first block start = exam_start - 45 - 15 = exam_start - 60
    exam_start = dt.datetime(2026, 5, 22, 14, 0, 0, tzinfo=dt.timezone.utc)
    result = ExamBracket.call({
        "exam_start_iso": "2026-05-22T14:00:00+00:00",
        "exam_end_iso": "2026-05-22T16:00:00+00:00",
    })
    first_start = dt.datetime.fromisoformat(result[0]["start_iso"])
    expected_start = exam_start - dt.timedelta(minutes=60)
    assert first_start == expected_start


def test_exam_bracket_custom_review_minutes():
    exam_start = dt.datetime(2026, 5, 22, 14, 0, 0, tzinfo=dt.timezone.utc)
    result = ExamBracket.call({
        "exam_start_iso": "2026-05-22T14:00:00+00:00",
        "exam_end_iso": "2026-05-22T16:00:00+00:00",
        "review_minutes": 30,
    })
    first_start = dt.datetime.fromisoformat(result[0]["start_iso"])
    expected_start = exam_start - dt.timedelta(minutes=45)  # 30 + 15
    assert first_start == expected_start
