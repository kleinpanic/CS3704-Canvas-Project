"""Tests for plot widgets — bar charts, braille plots, gauges, weight bars."""

from canvas_tui.theme import get_theme
from canvas_tui.widgets.plots import (
    BarEntry,
    PlotSeries,
    WeightSegment,
    grade_color,
    render_bar_chart,
    render_braille_plot,
    render_gauge,
    render_weight_bar,
    sparkline,
    urgency_color,
)


class TestGradeColor:
    def test_a_grade(self):
        t = get_theme()
        assert grade_color(95) == t.success

    def test_b_grade(self):
        t = get_theme()
        assert grade_color(85) == t.info

    def test_c_grade(self):
        t = get_theme()
        assert grade_color(75) == t.warning

    def test_d_grade(self):
        t = get_theme()
        assert grade_color(65) == t.secondary

    def test_f_grade(self):
        t = get_theme()
        assert grade_color(50) == t.error

    def test_boundary_90(self):
        t = get_theme()
        assert grade_color(90) == t.success

    def test_boundary_80(self):
        t = get_theme()
        assert grade_color(80) == t.info


class TestUrgencyColor:
    def test_many(self):
        t = get_theme()
        assert urgency_color(10) == t.error

    def test_several(self):
        t = get_theme()
        assert urgency_color(7) == t.warning

    def test_some(self):
        t = get_theme()
        assert urgency_color(4) == t.info

    def test_few(self):
        t = get_theme()
        assert urgency_color(2) == t.info

    def test_none(self):
        t = get_theme()
        assert urgency_color(0) == t.success


class TestBarChart:
    def test_empty(self):
        result = render_bar_chart([])
        assert "No data" in result

    def test_single_entry(self):
        entries = [BarEntry(label="CS101", value=85.0)]
        result = render_bar_chart(entries, bar_width=20)
        assert "CS101" in result
        assert "█" in result
        assert "85.0%" in result

    def test_multiple_entries(self):
        entries = [
            BarEntry(label="CS101", value=95.0),
            BarEntry(label="MATH", value=72.0),
            BarEntry(label="ENG", value=45.0),
        ]
        result = render_bar_chart(entries, bar_width=20)
        assert "CS101" in result
        assert "MATH" in result
        assert "ENG" in result

    def test_with_title(self):
        entries = [BarEntry(label="X", value=50)]
        result = render_bar_chart(entries, title="My Chart")
        assert "My Chart" in result

    def test_custom_suffix(self):
        entries = [BarEntry(label="X", value=80, suffix="A-")]
        result = render_bar_chart(entries)
        assert "A-" in result

    def test_clamps_values(self):
        entries = [BarEntry(label="Over", value=150)]
        result = render_bar_chart(entries, bar_width=10)
        assert "█" in result  # Should be full bar (clamped to 100)


class TestGauge:
    def test_basic(self):
        result = render_gauge(8, 12, width=20)
        assert "8/12" in result
        assert "67%" in result
        assert "█" in result

    def test_zero_total(self):
        result = render_gauge(0, 0)
        assert "no assignments" in result

    def test_full_completion(self):
        result = render_gauge(10, 10, width=10)
        assert "100%" in result

    def test_with_label(self):
        result = render_gauge(5, 10, label="CS101")
        assert "CS101" in result


class TestWeightBar:
    def test_empty(self):
        result = render_weight_bar([])
        assert "No weight" in result

    def test_basic(self):
        segments = [
            WeightSegment(label="HW", weight=40),
            WeightSegment(label="Exam", weight=30),
            WeightSegment(label="Quiz", weight=20),
            WeightSegment(label="Part", weight=10),
        ]
        result = render_weight_bar(segments, width=40)
        assert "HW" in result
        assert "Exam" in result
        assert "40%" in result

    def test_with_title(self):
        segments = [WeightSegment(label="HW", weight=100)]
        result = render_weight_bar(segments, title="Weights")
        assert "Weights" in result

    def test_auto_colors(self):
        segments = [
            WeightSegment(label="A", weight=50),
            WeightSegment(label="B", weight=50),
        ]
        result = render_weight_bar(segments)
        assert "█" in result


class TestBraillePlot:
    def test_empty(self):
        result = render_braille_plot([])
        assert "No data" in result

    def test_empty_series(self):
        result = render_braille_plot([PlotSeries(values=[], label="empty")])
        assert "No data" in result

    def test_single_series(self):
        series = [PlotSeries(values=[10, 20, 30, 40, 50], color="cyan", label="Test")]
        result = render_braille_plot(series, width=20, height=4)
        assert any(0x2800 <= ord(c) <= 0x28FF for c in result)
        assert "Test" in result

    def test_multiple_series_overlay(self):
        """Multiple series should be overlaid on the same grid, not stacked."""
        series = [
            PlotSeries(values=[10, 20, 30], color="cyan", label="A"),
            PlotSeries(values=[30, 20, 10], color="green", label="B"),
        ]
        result = render_braille_plot(series, width=15, height=3)
        assert "A" in result
        assert "B" in result
        # The overlay should produce braille chars with dots from both series
        braille_chars = [c for c in result if 0x2800 <= ord(c) <= 0x28FF and c != chr(0x2800)]
        assert len(braille_chars) > 0

    def test_with_title(self):
        series = [PlotSeries(values=[1, 2, 3])]
        result = render_braille_plot(series, title="My Plot")
        assert "My Plot" in result

    def test_constant_values(self):
        series = [PlotSeries(values=[50, 50, 50])]
        result = render_braille_plot(series, width=10, height=3)
        assert isinstance(result, str)

    def test_y_axis_labels(self):
        series = [PlotSeries(values=[0, 50, 100])]
        result = render_braille_plot(series, y_min=0, y_max=100)
        assert "100" in result
        assert "0" in result


class TestSparkline:
    def test_empty(self):
        assert sparkline([]) == ""

    def test_ascending(self):
        result = sparkline([0, 25, 50, 75, 100])
        assert "▁" in result
        assert "█" in result

    def test_constant(self):
        result = sparkline([50, 50, 50])
        assert "▁" in result or "▄" in result or "█" in result

    def test_with_color(self):
        result = sparkline([1, 2, 3], color="red")
        assert "[red]" in result
