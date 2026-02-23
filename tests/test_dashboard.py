"""Tests for dashboard screen data rendering logic."""

from __future__ import annotations

from canvas_tui.widgets.plots import (
    BarEntry,
    PlotSeries,
    render_bar_chart,
    render_braille_plot,
    render_gauge,
    urgency_color,
)


class TestDashboardDataRendering:
    """Test the rendering functions used by the dashboard."""

    def test_course_score_bars(self):
        """Simulate course score bar chart generation."""
        entries = [
            BarEntry(label="CS3214", value=92.3, suffix="92.3%"),
            BarEntry(label="MATH2114", value=78.5, suffix="78.5%"),
            BarEntry(label="ENGL1106", value=88.1, suffix="88.1%"),
        ]
        result = render_bar_chart(entries, bar_width=25, title="Course Scores")
        assert "Course Scores" in result
        assert "CS3214" in result
        assert "92.3%" in result
        assert "█" in result

    def test_urgency_coloring(self):
        """Test urgency color thresholds for due-soon panel."""
        assert urgency_color(0) == "green"
        assert urgency_color(3) == "cyan"
        assert urgency_color(5) == "blue"
        assert urgency_color(8) == "yellow"
        assert urgency_color(12) == "red"

    def test_completion_gauges(self):
        """Test assignment completion gauge rendering."""
        # Course with good completion
        result = render_gauge(15, 18, width=20, label="CS3214")
        assert "CS3214" in result
        assert "15/18" in result
        assert "83%" in result

        # Course with no assignments
        result = render_gauge(0, 0, label="NEW101")
        assert "no assignments" in result

    def test_grade_trend_plot(self):
        """Test braille plot for grade trends."""
        series = [
            PlotSeries(values=[85, 90, 78, 92, 88], color="cyan", label="CS3214"),
            PlotSeries(values=[70, 75, 72, 80, 68], color="yellow", label="MATH2114"),
        ]
        result = render_braille_plot(
            series, width=30, height=5,
            title="Grade Trends", y_min=0, y_max=100,
        )
        assert "Grade Trends" in result
        assert "CS3214" in result
        assert "MATH2114" in result
        assert "100" in result  # y-axis label

    def test_empty_dashboard_data(self):
        """Dashboard with no courses should render gracefully."""
        assert "No data" in render_bar_chart([])
        result = render_braille_plot([])
        assert "No data" in result
