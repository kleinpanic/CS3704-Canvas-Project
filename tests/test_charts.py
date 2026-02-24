"""Tests for plotext chart rendering."""

from canvas_tui.widgets.charts import (
    completion_bullet,
    grade_histogram,
    multi_line_chart,
    scatter_scores,
    score_bar_chart,
    score_line_chart,
    weekly_activity_chart,
)


class TestCharts:
    def test_score_bar_chart_renders(self):
        result = score_bar_chart(["CS", "MATH"], [92.5, 78.0], width=40, height=8)
        assert "CS" in result
        assert "MATH" in result

    def test_score_bar_chart_empty(self):
        result = score_bar_chart([], [], width=40, height=8)
        assert "No score data" in result

    def test_line_chart_renders(self):
        result = score_line_chart(["a1", "a2", "a3"], [85, 90, 88], width=40, height=8)
        assert result  # Non-empty ANSI output

    def test_line_chart_empty(self):
        result = score_line_chart([], [], width=40, height=8)
        assert "No trend data" in result

    def test_multi_line(self):
        result = multi_line_chart(
            {"CS": [85, 90, 88], "MATH": [70, 75, 80]},
            width=40, height=8,
        )
        assert result

    def test_histogram(self):
        result = grade_histogram([85, 90, 78, 92, 88, 95], width=40, height=8)
        assert result

    def test_histogram_empty(self):
        result = grade_histogram([], width=40, height=8)
        assert "No grade data" in result

    def test_scatter(self):
        result = scatter_scores([1, 2, 3], [85, 90, 88], width=40, height=8)
        assert result

    def test_completion_bullet(self):
        result = completion_bullet(["CS", "MATH"], [85, 60], width=40, height=8)
        assert result

    def test_weekly_activity(self):
        result = weekly_activity_chart(
            ["Mon", "Tue", "Wed"], [3, 5, 2], width=40, height=8,
        )
        assert result


class TestCommandBar:
    def test_pages_exist(self):
        from canvas_tui.widgets.command_bar import PAGES
        assert len(PAGES) >= 4
        assert PAGES[0][0] == "Navigation"
        assert PAGES[1][0] == "Views"
        assert PAGES[3][0] == "Pomodoro"
