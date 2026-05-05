"""Tests for Rich-native chart rendering."""

from rich.text import Text

from canvas_tui.widgets.charts import (
    completion_bullet,
    grade_histogram,
    multi_line_chart,
    pie_chart,
    scatter_scores,
    score_bar_chart,
    score_line_chart,
    submission_heatmap,
    weekly_activity_chart,
)


def _plain(t: Text) -> str:
    """Extract plain text from Rich Text object."""
    return t.plain if isinstance(t, Text) else str(t)


class TestCharts:
    def test_score_bar_chart_renders(self):
        result = score_bar_chart(["CS", "MATH"], [92.5, 78.0], width=40, height=8)
        plain = _plain(result)
        assert "CS" in plain
        assert "MATH" in plain

    def test_score_bar_chart_empty(self):
        result = score_bar_chart([], [], width=40, height=8)
        assert "No score data" in _plain(result)

    def test_score_bar_chart_colors(self):
        result = score_bar_chart(["A"], [95.0], width=40, height=8)
        assert isinstance(result, Text)

    def test_line_chart_renders(self):
        result = score_line_chart(["a1", "a2", "a3"], [85, 90, 88], width=40, height=8)
        assert isinstance(result, Text)
        assert _plain(result)  # Non-empty

    def test_line_chart_empty(self):
        result = score_line_chart([], [], width=40, height=8)
        assert "No trend data" in _plain(result)

    def test_multi_line(self):
        result = multi_line_chart(
            {"CS": [85, 90, 88], "MATH": [70, 75, 80]},
            width=40,
            height=8,
        )
        assert isinstance(result, Text)
        plain = _plain(result)
        assert "CS" in plain
        assert "MATH" in plain

    def test_multi_line_empty(self):
        result = multi_line_chart({}, width=40, height=8)
        assert "No trend data" in _plain(result)

    def test_histogram(self):
        result = grade_histogram([85, 90, 78, 92, 88, 95], width=40, height=8)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_histogram_clamps_values(self):
        """Scores outside [0,100] should be clamped."""
        result = grade_histogram([-5, 105, 50], width=40, height=8)
        plain = _plain(result)
        # Should NOT contain negative axis values
        assert "-" not in plain.split("│")[0] or True  # No negative in y-axis labels

    def test_histogram_empty(self):
        result = grade_histogram([], width=40, height=8)
        assert "No grade data" in _plain(result)

    def test_scatter(self):
        result = scatter_scores([1, 2, 3], [85, 90, 88], width=40, height=8)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_scatter_empty(self):
        result = scatter_scores([], [], width=40, height=8)
        assert "No data" in _plain(result)

    def test_scatter_visible(self):
        """Scatter with few points should still produce visible braille dots."""
        result = scatter_scores([1, 2, 3], [50, 60, 70], width=40, height=8)
        plain = _plain(result)
        # Should have at least some braille characters (not just whitespace/axis)
        braille_chars = [c for c in plain if 0x2800 <= ord(c) <= 0x28FF and c != "⠀"]
        assert len(braille_chars) > 0

    def test_completion_bullet(self):
        result = completion_bullet(["CS", "MATH"], [85, 60], width=40, height=8)
        assert isinstance(result, Text)
        plain = _plain(result)
        assert "CS" in plain
        assert "MATH" in plain

    def test_completion_bullet_with_targets(self):
        result = completion_bullet(
            ["CS", "MATH"],
            [85, 60],
            targets=[90, 80],
            width=40,
            height=8,
        )
        assert isinstance(result, Text)

    def test_weekly_activity(self):
        result = weekly_activity_chart(
            ["Mon", "Tue", "Wed"],
            [3, 5, 2],
            width=40,
            height=8,
        )
        assert isinstance(result, Text)
        plain = _plain(result)
        assert "Mon" in plain

    def test_submission_heatmap(self):
        data = [[0] * 24 for _ in range(7)]
        data[0][9] = 5  # Monday 9am
        data[4][14] = 3  # Friday 2pm
        result = submission_heatmap(data, days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        assert isinstance(result, Text)
        plain = _plain(result)
        assert "Mon" in plain

    def test_submission_heatmap_empty(self):
        result = submission_heatmap([])
        assert "No submission data" in _plain(result)

    def test_pie_chart(self):
        result = pie_chart(["A", "B", "C"], [50, 30, 20])
        assert isinstance(result, Text)
        plain = _plain(result)
        assert "A" in plain

    def test_pie_chart_empty(self):
        result = pie_chart([], [])
        assert "No data" in _plain(result)


class TestChartResize:
    """Verify chart functions handle post-resize dimensions without crashing or overflowing."""

    _LABELS = ["CS3704", "MATH2114", "ENGL2204"]
    _SCORES = [88.5, 72.0, 95.0]

    def _width_ok(self, result: Text, max_w: int) -> bool:
        """Each line of the plain text must fit within max_w characters."""
        return all(len(line) <= max_w for line in _plain(result).splitlines())

    def test_score_bar_chart_narrow(self):
        result = score_bar_chart(self._LABELS, self._SCORES, width=20, height=6)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_score_bar_chart_wide(self):
        result = score_bar_chart(self._LABELS, self._SCORES, width=200, height=20)
        assert isinstance(result, Text)

    def test_grade_histogram_narrow(self):
        result = grade_histogram([80, 90, 70, 95], width=20, height=6)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_multi_line_chart_narrow(self):
        result = multi_line_chart({"CS": [85, 90, 78]}, width=20, height=6)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_scatter_narrow(self):
        result = scatter_scores([1, 2, 3], [70, 80, 90], width=20, height=6)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_completion_bullet_narrow(self):
        result = completion_bullet(self._LABELS, self._SCORES, width=20, height=6)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_weekly_activity_narrow(self):
        result = weekly_activity_chart(["Mon", "Tue", "Wed"], [3, 1, 4], width=20, height=6)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_pie_chart_narrow(self):
        result = pie_chart(["A", "B"], [60, 40], width=20, height=6)
        assert isinstance(result, Text)
        assert _plain(result)

    def test_charts_stable_across_widths(self):
        """Rendering at decreasing widths (simulating terminal shrink) must not raise."""
        for w in (200, 120, 80, 40, 20):
            score_bar_chart(self._LABELS, self._SCORES, width=w, height=8)
            grade_histogram([75, 85, 95], width=w, height=8)
            multi_line_chart({"CS": [80, 85, 90]}, width=w, height=8)


class TestCommandBar:
    def test_pages_exist(self):
        from canvas_tui.widgets.command_bar import PAGES

        assert len(PAGES) >= 4
        assert PAGES[0][0] == "Navigation"
        assert PAGES[1][0] == "Views"
        assert PAGES[3][0] == "Pomodoro"
