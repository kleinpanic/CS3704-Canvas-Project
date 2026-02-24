"""Terminal chart rendering via plotext.

All functions return Rich Text objects (via Text.from_ansi) ready for
Textual Static widgets. plotext renders to ANSI escape codes which we
convert to Rich's internal format for proper display.
"""

from __future__ import annotations

import plotext as plt
from rich.text import Text


def _to_rich(ansi_str: str) -> Text:
    """Convert plotext ANSI output to Rich Text for Textual widgets."""
    return Text.from_ansi(ansi_str)


def _setup(width: int = 50, height: int = 12, title: str = "") -> None:
    """Common plotext setup."""
    plt.clf()
    plt.theme("dark")
    plt.plotsize(width, height)
    if title:
        plt.title(title)


def score_bar_chart(
    labels: list[str],
    scores: list[float],
    width: int = 50,
    height: int = 12,
    title: str = "Course Scores",
) -> Text:
    """Horizontal bar chart of course scores."""
    if not labels:
        return Text("No score data", style="dim")
    _setup(width, height, title)
    colors = []
    for s in scores:
        if s >= 90:
            colors.append("green")
        elif s >= 80:
            colors.append("cyan")
        elif s >= 70:
            colors.append("yellow")
        else:
            colors.append("red")
    plt.bar(labels, scores, color=colors, orientation="horizontal")
    plt.xlim(0, 100)
    return _to_rich(plt.build())


def score_line_chart(
    labels: list[str],
    values: list[float],
    width: int = 50,
    height: int = 10,
    title: str = "Score Trend",
    color: str = "cyan",
) -> Text:
    """Line chart of scores over assignments."""
    if not values:
        return Text("No trend data", style="dim")
    _setup(width, height, title)
    x = list(range(1, len(values) + 1))
    plt.plot(x, values, color=color, marker="braille")
    plt.ylim(0, 100)
    return _to_rich(plt.build())


def multi_line_chart(
    series: dict[str, list[float]],
    width: int = 50,
    height: int = 12,
    title: str = "Grade Trends",
) -> Text:
    """Multiple line series on one chart."""
    if not series:
        return Text("No trend data", style="dim")
    _setup(width, height, title)
    colors = ["cyan", "green", "yellow", "magenta", "blue", "red"]
    for i, (label, vals) in enumerate(series.items()):
        if vals:
            x = list(range(1, len(vals) + 1))
            plt.plot(x, vals, color=colors[i % len(colors)], label=label, marker="braille")
    plt.ylim(0, 100)
    return _to_rich(plt.build())


def grade_histogram(
    scores: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "Grade Distribution",
    bins: int = 10,
) -> Text:
    """Histogram of grade scores."""
    if not scores:
        return Text("No grade data", style="dim")
    _setup(width, height, title)
    plt.hist(scores, bins=bins, color="cyan")
    return _to_rich(plt.build())


def submission_heatmap(
    day_hour_counts: list[list[int]],
    days: list[str] | None = None,
    hours: list[str] | None = None,
    width: int = 50,
    height: int = 12,
    title: str = "Submission Activity",
) -> Text:
    """Heatmap of submission patterns (day x hour)."""
    if not day_hour_counts:
        return Text("No submission data", style="dim")
    _setup(width, height, title)
    plt.matrix_plot(day_hour_counts)
    if days:
        plt.yticks(list(range(len(days))), days)
    if hours:
        plt.xticks(list(range(len(hours))), hours)
    return _to_rich(plt.build())


def completion_bullet(
    labels: list[str],
    actual: list[float],
    targets: list[float] | None = None,
    width: int = 50,
    height: int = 10,
    title: str = "Completion",
) -> Text:
    """Bullet chart showing actual vs target completion."""
    if not labels:
        return Text("No data", style="dim")
    _setup(width, height, title)
    plt.bar(labels, actual, color="cyan", orientation="horizontal")
    if targets:
        plt.bar(labels, targets, color="gray", orientation="horizontal")
    plt.xlim(0, 100)
    return _to_rich(plt.build())


def scatter_scores(
    x: list[float],
    y: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "Score Scatter",
    color: str = "cyan",
) -> Text:
    """Scatter plot of scores."""
    if not x or not y:
        return Text("No data", style="dim")
    _setup(width, height, title)
    plt.scatter(x, y, color=color, marker="braille")
    return _to_rich(plt.build())


def pie_chart(
    labels: list[str],
    values: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "",
) -> Text:
    """Simulated pie chart using horizontal stacked bars."""
    if not labels or not values:
        return Text("No data", style="dim")
    _setup(width, height, title)
    colors = ["cyan", "green", "yellow", "magenta", "blue", "red", "white"]
    total = sum(values)
    if total <= 0:
        return Text("No data", style="dim")
    pcts = [100.0 * v / total for v in values]
    plt.stacked_bar([""], [pcts], color=colors[: len(labels)], orientation="horizontal", labels=labels)
    return _to_rich(plt.build())


def weekly_activity_chart(
    days: list[str],
    counts: list[int],
    width: int = 40,
    height: int = 8,
    title: str = "This Week",
) -> Text:
    """Bar chart of submissions per day this week."""
    if not days:
        return Text("No data", style="dim")
    _setup(width, height, title)
    plt.bar(days, counts, color="cyan")
    return _to_rich(plt.build())
