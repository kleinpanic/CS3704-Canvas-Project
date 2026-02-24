"""Terminal chart rendering via plotext.

All functions return ANSI strings ready for Rich/Textual Static widgets.
plotext renders directly to terminal escape codes — we capture the output
with plt.build() and embed it.
"""

from __future__ import annotations

import plotext as plt


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
) -> str:
    """Horizontal bar chart of course scores."""
    if not labels:
        return "[dim]No score data[/dim]"
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
    return plt.build()


def score_line_chart(
    labels: list[str],
    values: list[float],
    width: int = 50,
    height: int = 10,
    title: str = "Score Trend",
    color: str = "cyan",
) -> str:
    """Line chart of scores over assignments."""
    if not values:
        return "[dim]No trend data[/dim]"
    _setup(width, height, title)
    x = list(range(1, len(values) + 1))
    plt.plot(x, values, color=color, marker="braille")
    plt.ylim(0, 100)
    return plt.build()


def multi_line_chart(
    series: dict[str, list[float]],
    width: int = 50,
    height: int = 12,
    title: str = "Grade Trends",
) -> str:
    """Multiple line series on one chart."""
    if not series:
        return "[dim]No trend data[/dim]"
    _setup(width, height, title)
    colors = ["cyan", "green", "yellow", "magenta", "blue", "red"]
    for i, (label, vals) in enumerate(series.items()):
        if vals:
            x = list(range(1, len(vals) + 1))
            plt.plot(x, vals, color=colors[i % len(colors)], label=label, marker="braille")
    plt.ylim(0, 100)
    return plt.build()


def grade_histogram(
    scores: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "Grade Distribution",
    bins: int = 10,
) -> str:
    """Histogram of grade scores."""
    if not scores:
        return "[dim]No grade data[/dim]"
    _setup(width, height, title)
    plt.hist(scores, bins=bins, color="cyan")
    return plt.build()


def submission_heatmap(
    day_hour_counts: list[list[int]],
    days: list[str] | None = None,
    hours: list[str] | None = None,
    width: int = 50,
    height: int = 12,
    title: str = "Submission Activity",
) -> str:
    """Heatmap of submission patterns (day x hour).

    day_hour_counts: 7 x 24 matrix of submission counts.
    """
    if not day_hour_counts:
        return "[dim]No submission data[/dim]"
    _setup(width, height, title)
    plt.matrix_plot(day_hour_counts)
    if days:
        plt.yticks(list(range(len(days))), days)
    if hours:
        plt.xticks(list(range(len(hours))), hours)
    return plt.build()


def completion_bullet(
    labels: list[str],
    actual: list[float],
    targets: list[float] | None = None,
    width: int = 50,
    height: int = 10,
    title: str = "Completion",
) -> str:
    """Bullet chart showing actual vs target completion."""
    if not labels:
        return "[dim]No data[/dim]"
    _setup(width, height, title)
    plt.bar(labels, actual, color="cyan", orientation="horizontal")
    if targets:
        plt.bar(labels, targets, color="gray", orientation="horizontal")
    plt.xlim(0, 100)
    return plt.build()


def scatter_scores(
    x: list[float],
    y: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "Score Scatter",
    color: str = "cyan",
) -> str:
    """Scatter plot of scores."""
    if not x or not y:
        return "[dim]No data[/dim]"
    _setup(width, height, title)
    plt.scatter(x, y, color=color, marker="braille")
    return plt.build()


def pie_chart(
    labels: list[str],
    values: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "",
) -> str:
    """Simulated pie chart using horizontal stacked bars."""
    if not labels or not values:
        return "[dim]No data[/dim]"
    _setup(width, height, title)
    colors = ["cyan", "green", "yellow", "magenta", "blue", "red", "white"]
    total = sum(values)
    if total <= 0:
        return "[dim]No data[/dim]"
    pcts = [100.0 * v / total for v in values]
    # Render as stacked horizontal bar
    plt.stacked_bar([""], [pcts], color=colors[: len(labels)], orientation="horizontal", labels=labels)
    return plt.build()


def weekly_activity_chart(
    days: list[str],
    counts: list[int],
    width: int = 40,
    height: int = 8,
    title: str = "This Week",
) -> str:
    """Bar chart of submissions per day this week."""
    if not days:
        return "[dim]No data[/dim]"
    _setup(width, height, title)
    plt.bar(days, counts, color="cyan")
    return plt.build()
