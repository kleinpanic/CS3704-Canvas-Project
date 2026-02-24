"""Tests for course management and ghost detection."""

from canvas_tui.screens.courses import is_likely_ghost


class TestGhostDetection:
    def test_advising_is_ghost(self):
        ghost, reason = is_likely_ghost("ADVISING", "Emily's Everything Neuroscience Advising", 0)
        assert ghost
        assert "advising" in reason.lower()

    def test_lockdown_browser_is_ghost(self):
        ghost, _ = is_likely_ghost("LDB", "Lockdown Browser Info", 0)
        assert ghost

    def test_old_semester_is_ghost(self):
        ghost, reason = is_likely_ghost("CHEM101", "General Chemistry Fall 2020", 0)
        assert ghost
        assert "old semester" in reason or "2020" in reason

    def test_csvc_is_ghost(self):
        ghost, _ = is_likely_ghost("CSVC", "CSVC", 0)
        assert ghost

    def test_followup_is_ghost(self):
        ghost, _ = is_likely_ghost("FU", "Follow-up Group Design Appreciation Fall 2023", 0)
        assert ghost

    def test_zero_assignments_is_ghost(self):
        ghost, reason = is_likely_ghost("IFC", "IFC 2023", 0)
        assert ghost

    def test_real_course_not_ghost(self):
        ghost, _ = is_likely_ghost("CS3214", "Computer Systems", 15)
        assert not ghost

    def test_real_course_with_assignments(self):
        ghost, _ = is_likely_ghost("MATH2114", "Intro Linear Algebra", 8)
        assert not ghost

    def test_makeup_test_is_ghost(self):
        ghost, _ = is_likely_ghost("CHEM", "General Chemistry Makeup Test 4 Spring 2023", 0)
        assert ghost

    def test_sandbox_is_ghost(self):
        ghost, _ = is_likely_ghost("TEST", "Test Course Sandbox", 0)
        assert ghost

    def test_tutorial_is_ghost(self):
        ghost, _ = is_likely_ghost("TUT", "Canvas Tutorial", 0)
        assert ghost


class TestCourseHiding:
    def test_toggle_course(self, tmp_dir):
        import os
        from canvas_tui.state import StateManager

        sm = StateManager(os.path.join(tmp_dir, "state.json"))
        assert not sm.is_course_hidden(12345)

        result = sm.toggle_course_hidden(12345)
        assert result is True
        assert sm.is_course_hidden(12345)

        result = sm.toggle_course_hidden(12345)
        assert result is False
        assert not sm.is_course_hidden(12345)

    def test_get_hidden_courses(self, tmp_dir):
        import os
        from canvas_tui.state import StateManager

        sm = StateManager(os.path.join(tmp_dir, "state.json"))
        sm.set_hidden_courses([111, 222, 333])
        assert sm.get_hidden_courses() == [111, 222, 333]

    def test_hidden_persists(self, tmp_dir):
        import os
        from canvas_tui.state import StateManager

        path = os.path.join(tmp_dir, "state.json")
        sm1 = StateManager(path)
        sm1.toggle_course_hidden(999)

        sm2 = StateManager(path)
        assert sm2.is_course_hidden(999)
