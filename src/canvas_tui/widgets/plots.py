"""Terminal chart widgets — bar charts, braille line plots, progress gauges.

All rendering uses Rich markup — no external charting libraries.
Inspired by GideonWolfe/canvas-tui's termui gauge/barchart/plot widgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..theme import get_theme


# ─── Color thresholds (theme-aware) ──────────────────────────────────────
def grade_color(pct: float) -> str:
    """Return Rich color name for a grade percentage."""
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


def urgency_color(count: int) -> str:
    """Return color based on due-item count."""
    t = get_theme()
    if count >= 10:
        return t.error
    if count >= 7:
        return t.warning
    if count >= 4:
        return t.info
    if count >= 2:
        return t.info
    return t.success


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
    color: str = ""


def _chart_palette() -> list[str]:
    """Return chart color palette from theme."""
    t = get_theme()
    return [t.info, t.success, t.warning, t.secondary, t.primary, t.error, t.text_accent, t.text_muted]


def render_weight_bar(
    segments: list[WeightSegment],
    width: int = 40,
    title: str = "",
) -> str:
    """Render a stacked horizontal bar showing assignment group weights."""
    if not segments:
        return "[dim]No weight data[/dim]"

    lines: list[str] = []
    if title:
        lines.append(f"[bold]{title}[/bold]")

    palette = _chart_palette()

    # Auto-assign colors if not set
    for i, seg in enumerate(segments):
        if not seg.color:
            seg.color = palette[i % len(palette)]

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


# ─── Braille Line Plot (FIXED — overlaid series on shared grid) ──────────
# Unicode braille characters: 2x4 dot matrix per character
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
    color: str = ""
    label: str = ""


def render_braille_plot(
    series_list: list[PlotSeries],
    width: int = 40,
    height: int = 8,
    title: str = "",
    y_min: float | None = None,
    y_max: float | None = None,
) -> str:
    """Render a braille-dot line plot with ALL series overlaid on one grid.

    Each character cell is 2 dots wide x 4 dots tall, so:
      - plot_dots_x = width * 2
      - plot_dots_y = height * 4
    """
    if not series_list or all(len(s.values) == 0 for s in series_list):
        return "[dim]No data to plot[/dim]"

    t = get_theme()
    palette = _chart_palette()

    # Auto-assign colors
    for i, s in enumerate(series_list):
        if not s.color:
            s.color = palette[i % len(palette)]

    all_vals = [v for s in series_list for v in s.values]
    lo = y_min if y_min is not None else min(all_vals)
    hi = y_max if y_max is not None else max(all_vals)
    if hi <= lo:
        hi = lo + 1.0

    dots_x = width * 2
    dots_y = height * 4
    y_range = hi - lo

    # Single shared grid for ALL series
    grid = [[0] * width for _ in range(height)]

    for s in series_list:
        if not s.values:
            continue
        n = len(s.values)
        for i, v in enumerate(s.values):
            dx = int(i / max(1, n - 1) * (dots_x - 1)) if n > 1 else dots_x // 2
            norm = max(0.0, min(1.0, (v - lo) / y_range))
            dy = dots_y - 1 - int(norm * (dots_y - 1))

            cx = min(dx // 2, width - 1)
            cy = min(dy // 4, height - 1)
            rx = dx % 2
            ry = dy % 4

            grid[cy][cx] |= _DOT_MAP[ry][rx]

    # Render with primary series color (braille cells can't be multi-colored per cell)
    primary_color = series_list[0].color if series_list else t.info

    lines: list[str] = []
    if title:
        lines.append(f"[bold]{title}[/bold]")

    # Y axis labels
    lines.append(f"  [dim]{hi:.0f}[/dim]")
    for row in grid:
        chars = "".join(chr(_BRAILLE_BASE + cell) for cell in row)
        lines.append(f"  [{primary_color}]{chars}[/{primary_color}]")
    lines.append(f"  [dim]{lo:.0f}[/dim]")

    # Legend
    legend_parts = []
    for s in series_list:
        if s.label:
            legend_parts.append(f"[{s.color}]■ {s.label}[/{s.color}]")
    if legend_parts:
        lines.append("  " + "  ".join(legend_parts))

    return "\n".join(lines)


# ─── Sparkline (enhanced) ───────────────────────────────────────────────
def sparkline(values: list[float], color: str = "") -> str:
    """Render a sparkline from raw values."""
    if not values:
        return ""
    if not color:
        color = get_theme().info
    chars = "▁▂▃▄▅▆▇█"
    lo = min(values)
    hi = max(values)
    rng = hi - lo if hi > lo else 1.0
    parts: list[str] = []
    for v in values:
        idx = int((v - lo) / rng * (len(chars) - 1))
        parts.append(chars[idx])
    return f"[{color}]{''.join(parts)}[/{color}]"
