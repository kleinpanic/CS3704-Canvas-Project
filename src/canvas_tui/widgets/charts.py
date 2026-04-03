"""Terminal chart rendering — Rich-native implementation.

All functions return Rich Text objects ready for Textual Static widgets.
No external charting libraries — uses Unicode block/braille characters
with Rich markup for colors.
"""

from __future__ import annotations

from rich.text import Text

from ..theme import get_theme


def _grade_color(pct: float) -> str:
    """Return Rich color for a grade percentage."""
    t = get_theme()
    if pct >= 90:
        return t.success
    if pct >= 80:
        return t.info
    if pct >= 70:
        return t.warning
    if pct >= 60:
        return t.secondary
    return t.error


def _chart_palette() -> list[str]:
    """Return the chart color palette from the current theme."""
    t = get_theme()
    return [t.info, t.success, t.warning, t.secondary, t.primary, t.error, t.text_accent, t.text_muted]


# ─── Horizontal Bar Chart ────────────────────────────────────────────────


def score_bar_chart(
    labels: list[str],
    scores: list[float],
    width: int = 50,
    height: int = 12,
    title: str = "Course Scores",
) -> Text:
    """Horizontal bar chart of course scores using block characters."""
    if not labels:
        return Text("No score data", style="dim")

    t = get_theme()
    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    max_label = max(len(l) for l in labels)
    bar_width = max(20, width - max_label - 12)

    for label, score in zip(labels, scores, strict=False):
        score = max(0.0, min(100.0, score))
        color = _grade_color(score)
        filled = int(score / 100.0 * bar_width)
        empty = bar_width - filled
        bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
        lines.append(f"  {label:<{max_label}}│{bar} {score:.1f}")

    # X-axis
    axis_pad = max_label + 3
    tick_positions = [0, 25, 50, 75, 100]
    axis_line = " " * axis_pad
    for tick in tick_positions:
        pos = int(tick / 100.0 * bar_width)
        # Place tick mark
        while len(axis_line) < axis_pad + pos:
            axis_line += "─"
        axis_line = axis_line[: axis_pad + pos] + "┼" + axis_line[axis_pad + pos + 1 :]
    lines.append(f"[dim]{axis_line}[/dim]")
    tick_labels = " " * axis_pad
    for tick in tick_positions:
        pos = int(tick / 100.0 * bar_width)
        lbl = str(tick)
        target = axis_pad + pos - len(lbl) // 2
        while len(tick_labels) < target:
            tick_labels += " "
        tick_labels += lbl
    lines.append(f"[dim]{tick_labels}[/dim]")

    return Text.from_markup("\n".join(lines))


# ─── Vertical Histogram ──────────────────────────────────────────────────


def grade_histogram(
    scores: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "Grade Distribution",
    bins: int = 10,
) -> Text:
    """Histogram of grade scores using vertical half-block bars."""
    if not scores:
        return Text("No grade data", style="dim")

    t = get_theme()
    # Clamp to valid range
    scores = [max(0.0, min(100.0, s)) for s in scores]

    # Build histogram bins manually
    bin_width = 100.0 / bins
    counts = [0] * bins
    for s in scores:
        idx = min(int(s / bin_width), bins - 1)
        counts[idx] += 1

    max_count = max(counts) if counts else 1
    chart_height = max(6, min(height - 4, 20))

    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    # Y-axis label width
    y_width = len(str(max_count)) + 1

    # Render rows top to bottom
    for row in range(chart_height, 0, -1):
        threshold = row / chart_height * max_count
        y_label = ""
        if row == chart_height:
            y_label = str(max_count)
        elif row == chart_height // 2:
            y_label = str(max_count // 2)
        elif row == 1:
            y_label = "0"

        parts = [f"[dim]{y_label:>{y_width}}│[/dim]"]
        for count in counts:
            if count >= threshold:
                parts.append(f"[{t.info}]██[/{t.info}]")
            elif count >= threshold - (max_count / chart_height / 2):
                parts.append(f"[{t.info}]▄▄[/{t.info}]")
            else:
                parts.append("  ")
        lines.append("".join(parts))

    # X-axis
    axis = f"[dim]{' ' * (y_width + 1)}{'──' * bins}[/dim]"
    lines.append(axis)

    # X-axis labels (bin edges)
    label_line = " " * (y_width + 1)
    step = max(1, bins // 5)
    for i in range(0, bins + 1, step):
        edge = int(i * bin_width)
        pos = i * 2
        lbl = str(edge)
        target = y_width + 1 + pos
        while len(label_line) < target:
            label_line += " "
        label_line = label_line[:target] + lbl + label_line[target + len(lbl) :]
    lines.append(f"[dim]{label_line}[/dim]")

    return Text.from_markup("\n".join(lines))


# ─── Multi-Line Chart (Braille) ──────────────────────────────────────────

_BRAILLE_BASE = 0x2800
_DOT_MAP = [
    [0x01, 0x08],  # row 0
    [0x02, 0x10],  # row 1
    [0x04, 0x20],  # row 2
    [0x40, 0x80],  # row 3
]


def _render_braille_grid(
    series: dict[str, list[float]],
    width: int,
    height: int,
    y_min: float = 0.0,
    y_max: float = 100.0,
) -> tuple[list[list[int]], dict[str, str]]:
    """Render multiple series onto a single braille grid.

    Returns (grid, color_map) where grid is height x width of braille dot patterns
    and color_map maps series labels to colors.
    """
    palette = _chart_palette()
    color_map: dict[str, str] = {}
    grid = [[0] * width for _ in range(height)]

    dots_x = width * 2
    dots_y = height * 4

    y_range = y_max - y_min
    if y_range <= 0:
        y_range = 1.0

    for i, (label, vals) in enumerate(series.items()):
        color_map[label] = palette[i % len(palette)]
        if not vals:
            continue

        n = len(vals)
        for j, v in enumerate(vals):
            # X position in dot-space
            dx = int(j / max(1, n - 1) * (dots_x - 1)) if n > 1 else dots_x // 2
            # Y position (inverted — 0 is top)
            norm = max(0.0, min(1.0, (v - y_min) / y_range))
            dy = dots_y - 1 - int(norm * (dots_y - 1))

            cx = min(dx // 2, width - 1)
            cy = min(dy // 4, height - 1)
            rx = dx % 2
            ry = dy % 4

            grid[cy][cx] |= _DOT_MAP[ry][rx]

    return grid, color_map


def multi_line_chart(
    series: dict[str, list[float]],
    width: int = 50,
    height: int = 12,
    title: str = "Grade Trends",
) -> Text:
    """Multiple line series on one chart using braille characters.

    All series are overlaid on a single shared grid.
    """
    if not series:
        return Text("No trend data", style="dim")

    t = get_theme()

    # Compute Y range from data
    all_vals = [v for vals in series.values() for v in vals]
    if not all_vals:
        return Text("No trend data", style="dim")

    y_min = max(0, min(all_vals) - 5)
    y_max = min(100, max(all_vals) + 5)

    chart_h = max(4, height - 5)  # Reserve space for title, axis, legend
    chart_w = max(20, width - 8)  # Reserve space for Y-axis labels

    grid, color_map = _render_braille_grid(series, chart_w, chart_h, y_min, y_max)

    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    # Use first series color for the dots (since braille can't be multi-colored per cell)
    # For better visual, cycle through colors per row (approximation)
    primary_color = next(iter(color_map.values())) if color_map else t.info

    # Y-axis + chart
    y_width = 6
    for row_idx, row in enumerate(grid):
        # Y-axis label
        if row_idx == 0:
            y_label = f"{y_max:.0f}"
        elif row_idx == len(grid) - 1:
            y_label = f"{y_min:.0f}"
        elif row_idx == len(grid) // 2:
            mid = (y_max + y_min) / 2
            y_label = f"{mid:.0f}"
        else:
            y_label = ""

        chars = "".join(chr(_BRAILLE_BASE + cell) for cell in row)
        lines.append(f"[dim]{y_label:>{y_width}}│[/dim][{primary_color}]{chars}[/{primary_color}]")

    # X-axis
    x_max = max(len(vals) for vals in series.values()) if series else 1
    x_axis = f"[dim]{' ' * (y_width + 1)}{'─' * chart_w}[/dim]"
    lines.append(x_axis)

    # X-axis labels
    x_labels = f"[dim]{' ' * (y_width + 1)}1{' ' * (chart_w - len(str(x_max)) - 1)}{x_max}[/dim]"
    lines.append(x_labels)

    # Legend
    legend_parts = []
    for label, color in color_map.items():
        legend_parts.append(f"[{color}]■ {label}[/{color}]")
    if legend_parts:
        lines.append("  " + "  ".join(legend_parts))

    return Text.from_markup("\n".join(lines))


# ─── Scatter Plot (Braille) ──────────────────────────────────────────────


def scatter_scores(
    x: list[float],
    y: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "Score Scatter",
    color: str = "",
) -> Text:
    """Scatter plot using braille characters."""
    if not x or not y:
        return Text("No data", style="dim")

    t = get_theme()
    dot_color = color or t.info

    chart_h = max(4, height - 4)
    chart_w = max(20, width - 8)

    y_min, y_max = 0.0, 100.0
    x_min, x_max = min(x), max(x)
    if x_max <= x_min:
        x_max = x_min + 1

    dots_x = chart_w * 2
    dots_y = chart_h * 4
    grid = [[0] * chart_w for _ in range(chart_h)]

    for xi, yi in zip(x, y, strict=False):
        # Normalize
        nx = (xi - x_min) / (x_max - x_min)
        ny = max(0.0, min(1.0, (yi - y_min) / (y_max - y_min)))

        dx = int(nx * (dots_x - 1))
        dy = dots_y - 1 - int(ny * (dots_y - 1))

        cx = min(dx // 2, chart_w - 1)
        cy = min(dy // 4, chart_h - 1)
        rx = dx % 2
        ry = dy % 4

        grid[cy][cx] |= _DOT_MAP[ry][rx]

    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    y_width = 6
    for row_idx, row in enumerate(grid):
        if row_idx == 0:
            y_label = f"{y_max:.0f}"
        elif row_idx == len(grid) - 1:
            y_label = f"{y_min:.0f}"
        else:
            y_label = ""
        chars = "".join(chr(_BRAILLE_BASE + cell) for cell in row)
        lines.append(f"[dim]{y_label:>{y_width}}│[/dim][{dot_color}]{chars}[/{dot_color}]")

    lines.append(f"[dim]{' ' * (y_width + 1)}{'─' * chart_w}[/dim]")
    lines.append(
        f"[dim]{' ' * (y_width + 1)}{x_min:.0f}{' ' * (chart_w - len(f'{x_min:.0f}') - len(f'{x_max:.0f}'))}{x_max:.0f}[/dim]"
    )

    return Text.from_markup("\n".join(lines))


# ─── Submission Heatmap ──────────────────────────────────────────────────


def submission_heatmap(
    day_hour_counts: list[list[int]],
    days: list[str] | None = None,
    hours: list[str] | None = None,
    width: int = 50,
    height: int = 12,
    title: str = "Submission Activity",
) -> Text:
    """Heatmap using colored block characters."""
    if not day_hour_counts:
        return Text("No submission data", style="dim")

    t = get_theme()
    # Find max for color scaling
    max_val = max(max(row) for row in day_hour_counts) if day_hour_counts else 1
    if max_val <= 0:
        max_val = 1

    day_labels = days or [f"D{i}" for i in range(len(day_hour_counts))]

    # Determine which hours to show (collapse to 6 buckets of 4 hours)
    n_hours = len(day_hour_counts[0]) if day_hour_counts else 24
    bucket_size = max(1, n_hours // 6)
    n_buckets = (n_hours + bucket_size - 1) // bucket_size

    heat_chars = " ░▒▓█"

    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    # Header with hour labels
    label_w = max(len(d) for d in day_labels) + 1
    hour_header = " " * label_w + "│"
    for b in range(n_buckets):
        h = b * bucket_size
        hour_header += f"{h:>3} "
    lines.append(f"[dim]{hour_header}[/dim]")

    for i, row in enumerate(day_hour_counts):
        label = day_labels[i] if i < len(day_labels) else ""
        parts = [f"[dim]{label:>{label_w - 1}} │[/dim]"]

        for b in range(n_buckets):
            start = b * bucket_size
            end = min(start + bucket_size, len(row))
            bucket_val = sum(row[start:end])

            intensity = bucket_val / max_val
            char_idx = min(int(intensity * (len(heat_chars) - 1)), len(heat_chars) - 1)

            if intensity > 0.7:
                color = t.success
            elif intensity > 0.4:
                color = t.info
            elif intensity > 0.1:
                color = t.text_muted
            else:
                color = t.panel

            char = heat_chars[char_idx]
            parts.append(f"[{color}]{char * 3} [{color}]")

        lines.append("".join(parts))

    return Text.from_markup("\n".join(lines))


# ─── Completion Bullet Chart ─────────────────────────────────────────────


def completion_bullet(
    labels: list[str],
    actual: list[float],
    targets: list[float] | None = None,
    width: int = 50,
    height: int = 10,
    title: str = "Completion",
) -> Text:
    """Bullet chart showing actual vs target with Rich bars."""
    if not labels:
        return Text("No data", style="dim")

    t = get_theme()
    # Default targets to 100% if not provided
    if not targets:
        targets = [100.0] * len(labels)

    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    max_label = max(len(l) for l in labels)
    bar_width = max(20, width - max_label - 12)

    for label, act, tgt in zip(labels, actual, targets, strict=False):
        act = max(0.0, min(100.0, act))
        tgt = max(0.0, min(100.0, tgt))

        filled = int(act / 100.0 * bar_width)
        target_pos = int(tgt / 100.0 * bar_width)
        empty = bar_width - filled

        color = _grade_color(act)

        # Build bar with target marker
        bar_chars = list(f"{'█' * filled}{'░' * empty}")
        if 0 <= target_pos < len(bar_chars):
            bar_chars[target_pos] = "│"

        bar_str = "".join(bar_chars[:filled])
        rest_str = "".join(bar_chars[filled:])
        bar = f"[{color}]{bar_str}[/{color}][dim]{rest_str}[/dim]"

        lines.append(f"  {label:<{max_label}}│{bar} {act:.0f}%")

    # X-axis
    axis_pad = max_label + 3
    lines.append(f"[dim]{' ' * axis_pad}{'─' * bar_width}[/dim]")
    tick_line = (
        " " * axis_pad
        + "0"
        + " " * (bar_width // 4 - 1)
        + "25"
        + " " * (bar_width // 4 - 2)
        + "50"
        + " " * (bar_width // 4 - 2)
        + "75"
        + " " * (bar_width // 4 - 3)
        + "100"
    )
    lines.append(f"[dim]{tick_line}[/dim]")

    return Text.from_markup("\n".join(lines))


# ─── Weekly Activity Chart ───────────────────────────────────────────────


def weekly_activity_chart(
    days: list[str],
    counts: list[int],
    width: int = 40,
    height: int = 8,
    title: str = "This Week",
) -> Text:
    """Vertical bar chart of activity per day using block characters."""
    if not days:
        return Text("No data", style="dim")

    t = get_theme()
    max_count = max(counts) if counts else 1
    if max_count <= 0:
        max_count = 1

    chart_h = max(4, height - 3)
    bar_w = max(2, (width - 4) // len(days) - 1)

    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    y_width = len(str(max_count)) + 1

    for row in range(chart_h, 0, -1):
        threshold = row / chart_h * max_count
        y_label = ""
        if row == chart_h:
            y_label = str(max_count)
        elif row == 1:
            y_label = "0"

        parts = [f"[dim]{y_label:>{y_width}}│[/dim]"]
        for count in counts:
            if count >= threshold:
                parts.append(f"[{t.info}]{'█' * bar_w}[/{t.info}] ")
            elif count >= threshold - (max_count / chart_h / 2):
                parts.append(f"[{t.info}]{'▄' * bar_w}[/{t.info}] ")
            else:
                parts.append(" " * (bar_w + 1))
        lines.append("".join(parts))

    # X-axis
    axis = f"[dim]{' ' * (y_width + 1)}"
    for _ in days:
        axis += "─" * bar_w + "┼"
    axis += "[/dim]"
    lines.append(axis)

    # Day labels
    label_line = " " * (y_width + 1)
    for d in days:
        label_line += f"{d:^{bar_w + 1}}"
    lines.append(f"[dim]{label_line}[/dim]")

    return Text.from_markup("\n".join(lines))


# ─── Score Line Chart ────────────────────────────────────────────────────


def score_line_chart(
    labels: list[str],
    values: list[float],
    width: int = 50,
    height: int = 10,
    title: str = "Score Trend",
    color: str = "",
) -> Text:
    """Single line chart using braille characters."""
    if not values:
        return Text("No trend data", style="dim")

    series = {"scores": values}
    return multi_line_chart(series, width, height, title)


# ─── Pie Chart (Stacked Bar Simulation) ──────────────────────────────────


def pie_chart(
    labels: list[str],
    values: list[float],
    width: int = 40,
    height: int = 10,
    title: str = "",
) -> Text:
    """Simulated pie chart using a stacked horizontal bar."""
    if not labels or not values:
        return Text("No data", style="dim")

    t = get_theme()
    total = sum(values)
    if total <= 0:
        return Text("No data", style="dim")

    palette = _chart_palette()
    bar_width = max(20, width - 4)

    lines: list[str] = []
    if title:
        lines.append(f"[bold {t.text}]{title}[/bold {t.text}]")

    bar_parts: list[str] = []
    legend_parts: list[str] = []
    for i, (label, val) in enumerate(zip(labels, values, strict=False)):
        pct = val / total
        chars = max(1, int(pct * bar_width))
        color = palette[i % len(palette)]
        bar_parts.append(f"[{color}]{'█' * chars}[/{color}]")
        legend_parts.append(f"[{color}]■ {label} ({pct:.0%})[/{color}]")

    lines.append("  " + "".join(bar_parts))
    # Wrap legend
    for i in range(0, len(legend_parts), 3):
        lines.append("  " + "  ".join(legend_parts[i : i + 3]))

    return Text.from_markup("\n".join(lines))
