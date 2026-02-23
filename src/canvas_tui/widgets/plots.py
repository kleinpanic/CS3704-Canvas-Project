"""Terminal chart widgets — bar charts, braille line plots, progress gauges.

All rendering uses Rich markup — no external charting libraries.
Inspired by GideonWolfe/canvas-tui's termui gauge/barchart/plot widgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ─── Color thresholds (GideonWolfe-style) ────────────────────────────────
def grade_color(pct: float) -> str:
    """Return Rich color name for a grade percentage."""
    if pct >= 90:
        return "green"
    if pct >= 80:
        return "cyan"
    if pct >= 70:
        return "yellow"
    if pct >= 60:
        return "magenta"
    return "red"


def urgency_color(count: int) -> str:
    """Return color based on due-item count (GideonWolfe style)."""
    if count >= 10:
        return "red"
    if count >= 7:
        return "yellow"
    if count >= 4:
        return "blue"
    if count >= 2:
        return "cyan"
    return "green"


# ─── Horizontal Bar Chart ────────────────────────────────────────────────
@dataclass
class BarEntry:
    """A single bar in a horizontal bar chart."""
    label: str
    value: float  # 0-100
    suffix: str = ""  # e.g. "85.2%"


def render_bar_chart(
    entries: list[BarEntry],
    bar_width: int = 30,
    title: str = "",
) -> str:
    """Render a horizontal bar chart using block characters.

    Example output:
        CS3214   ████████████████████░░░░░░  85.2%
        MATH2114 █████████████░░░░░░░░░░░░░  52.1%
    """
    if not entries:
        return "[dim]No data[/dim]"

    lines: list[str] = []
    if title:
        lines.append(f"[bold]{title}[/bold]")

    max_label = max(len(e.label) for e in entries) if entries else 8
    for e in entries:
        pct = max(0.0, min(100.0, e.value))
        filled = int(pct / 100.0 * bar_width)
        empty = bar_width - filled
        color = grade_color(pct)
        bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
        suffix = e.suffix or f"{pct:.1f}%"
        lines.append(f"  {e.label:<{max_label}}  {bar}  {suffix}")

    return "\n".join(lines)


# ─── Assignment Completion Gauge ─────────────────────────────────────────
def render_gauge(
    completed: int,
    total: int,
    width: int = 20,
    label: str = "",
) -> str:
    """Render a progress gauge: [████████░░░░] 8/12 (67%)"""
    if total <= 0:
        return f"  {label}  [dim]no assignments[/dim]" if label else "[dim]no assignments[/dim]"

    pct = 100.0 * completed / total
    filled = int(pct / 100.0 * width)
    empty = width - filled
    color = grade_color(pct)

    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
    text = f"{completed}/{total} ({pct:.0f}%)"
    if label:
        return f"  {label}  {bar}  {text}"
    return f"  {bar}  {text}"


# ─── Stacked Weight Bar ─────────────────────────────────────────────────
@dataclass
class WeightSegment:
    """A segment in a stacked weight bar."""
    label: str
    weight: float  # percentage 0-100
    color: str = "white"


# Distinct colors for up to 8 assignment groups
_WEIGHT_COLORS = ["cyan", "green", "yellow", "magenta", "blue", "red", "white", "bright_black"]


def render_weight_bar(
    segments: list[WeightSegment],
    width: int = 40,
    title: str = "",
) -> str:
    """Render a stacked horizontal bar showing assignment group weights.

    Example:
        ████████░░░░░░░░████░░░░░░░░████
        HW 40%     Exam 30%    Quiz 20%   Participation 10%
    """
    if not segments:
        return "[dim]No weight data[/dim]"

    lines: list[str] = []
    if title:
        lines.append(f"[bold]{title}[/bold]")

    # Auto-assign colors if not set
    for i, seg in enumerate(segments):
        if seg.color == "white":
            seg.color = _WEIGHT_COLORS[i % len(_WEIGHT_COLORS)]

    total_w = sum(s.weight for s in segments)
    if total_w <= 0:
        return "[dim]No weight data[/dim]"

    bar_parts: list[str] = []
    legend_parts: list[str] = []
    for seg in segments:
        chars = max(1, int(seg.weight / total_w * width))
        bar_parts.append(f"[{seg.color}]{'█' * chars}[/{seg.color}]")
        legend_parts.append(f"[{seg.color}]{seg.label} {seg.weight:.0f}%[/{seg.color}]")

    lines.append("  " + "".join(bar_parts))
    lines.append("  " + "  ".join(legend_parts))
    return "\n".join(lines)


# ─── Braille Line Plot ──────────────────────────────────────────────────
# Unicode braille characters: 2x4 dot matrix per character
# Dot positions:
#   ⠁ ⠈     row 0: (0,0)=0x01  (1,0)=0x08
#   ⠂ ⠐     row 1: (0,1)=0x02  (1,1)=0x10
#   ⠄ ⠠     row 2: (0,2)=0x04  (1,2)=0x20
#   ⡀ ⢀     row 3: (0,3)=0x40  (1,3)=0x80

_BRAILLE_BASE = 0x2800
_DOT_MAP = [
    [0x01, 0x08],  # row 0
    [0x02, 0x10],  # row 1
    [0x04, 0x20],  # row 2
    [0x40, 0x80],  # row 3
]


@dataclass
class PlotSeries:
    """A data series for the braille plot."""
    values: list[float] = field(default_factory=list)
    color: str = "cyan"
    label: str = ""


def render_braille_plot(
    series_list: list[PlotSeries],
    width: int = 40,
    height: int = 8,
    title: str = "",
    y_min: float | None = None,
    y_max: float | None = None,
) -> str:
    """Render a braille-dot line plot.

    Each character cell is 2 dots wide x 4 dots tall, so:
      - plot_dots_x = width * 2
      - plot_dots_y = height * 4
    """
    if not series_list or all(len(s.values) == 0 for s in series_list):
        return "[dim]No data to plot[/dim]"

    all_vals = [v for s in series_list for v in s.values]
    lo = y_min if y_min is not None else min(all_vals)
    hi = y_max if y_max is not None else max(all_vals)
    if hi <= lo:
        hi = lo + 1.0

    dots_x = width * 2
    dots_y = height * 4

    # Build a grid per series, then overlay
    # For simplicity with multiple colors, render each series separately
    # and combine as separate lines with labels
    lines: list[str] = []
    if title:
        lines.append(f"[bold]{title}[/bold]")

    for s in series_list:
        if not s.values:
            continue

        # Create empty grid
        grid = [[0] * width for _ in range(height)]

        # Map values to dot positions
        n = len(s.values)
        for i, v in enumerate(s.values):
            # x position in dot-space
            dx = int(i / max(1, n - 1) * (dots_x - 1)) if n > 1 else dots_x // 2
            # y position in dot-space (inverted — 0 is top)
            norm = (v - lo) / (hi - lo)
            dy = dots_y - 1 - int(norm * (dots_y - 1))

            # Map to character cell
            cx = dx // 2
            cy = dy // 4
            # Map to dot within cell
            rx = dx % 2
            ry = dy % 4

            if 0 <= cx < width and 0 <= cy < height:
                grid[cy][cx] |= _DOT_MAP[ry][rx]

        # Render grid to braille characters
        for row in grid:
            chars = "".join(chr(_BRAILLE_BASE + cell) for cell in row)
            lines.append(f"  [{s.color}]{chars}[/{s.color}]")

        if s.label:
            lines.append(f"  [{s.color}]── {s.label}[/{s.color}]")

    # Y axis labels
    if lines:
        lines.insert(1 if title else 0, f"  [dim]{hi:.0f}[/dim]")
        lines.append(f"  [dim]{lo:.0f}[/dim]")

    return "\n".join(lines)


# ─── Sparkline (enhanced) ───────────────────────────────────────────────
def sparkline(values: list[float], color: str = "cyan") -> str:
    """Render a sparkline from raw values."""
    if not values:
        return ""
    chars = "▁▂▃▄▅▆▇█"
    lo = min(values)
    hi = max(values)
    rng = hi - lo if hi > lo else 1.0
    parts: list[str] = []
    for v in values:
        idx = int((v - lo) / rng * (len(chars) - 1))
        parts.append(chars[idx])
    return f"[{color}]{''.join(parts)}[/{color}]"
