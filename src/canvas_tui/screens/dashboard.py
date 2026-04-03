"""Dashboard screen — landing page with logo, course scores, due-soon, trends.

Inspired by GideonWolfe/canvas-tui's dashboard.go layout:
- Top: Logo + summary bar chart
- Middle: Due-soon items with urgency coloring
- Bottom: Grade trends and completion gauges
"""

from __future__ import annotations

import contextlib
import datetime as dt
import threading
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..logo import get_logo
from ..models import CanvasItem
from ..widgets.plots import (
    BarEntry,
    PlotSeries,
    grade_color,
    render_bar_chart,
    render_braille_plot,
    render_gauge,
    sparkline,
    urgency_color,
)

if TYPE_CHECKING:
    from ..app import CanvasTUI


class DashboardScreen(Screen):
    """Overview dashboard — course scores, upcoming items, grade trends."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("r", "refresh_dash", "Refresh"),
        ("enter", "back_to_main", "Main view"),
    ]

    def __init__(self, owner_app: CanvasTUI) -> None:
        super().__init__()
        self._owner = owner_app
        self._loading = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dash-root"):
            with Horizontal(id="dash-top"):
                self.logo_panel = Static(id="dash-logo")
                yield self.logo_panel
                self.scores_panel = Static(id="dash-scores")
                yield self.scores_panel
            with Horizontal(id="dash-mid"):
                self.due_panel = Static(id="dash-due")
                yield self.due_panel
                self.completion_panel = Static(id="dash-completion")
                yield self.completion_panel
            self.trends_panel = Static(id="dash-trends")
            yield self.trends_panel
            yield Footer()

    def on_mount(self) -> None:
        logo_width = max(18, getattr(self.logo_panel.size, "width", 24) or 24)
        self.logo_panel.update(get_logo(width=logo_width, compact=True))
        self.scores_panel.update("[dim]Loading scores…[/dim]")
        self.due_panel.update("[dim]Loading…[/dim]")
        self.completion_panel.update("[dim]Loading completion…[/dim]")
        self.trends_panel.update("[dim]Loading trends…[/dim]")
        self._load_dashboard()

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def _load_dashboard(self) -> None:
        if self._loading:
            return
        self._loading = True

        def worker() -> None:
            try:
                courses = self._owner.course_cache
                items = self._owner.items

                # Fetch grades per course
                course_grades: dict[int, list[dict[str, Any]]] = {}
                for cid in courses:
                    with contextlib.suppress(Exception):
                        course_grades[cid] = self._owner.api.fetch_grades(cid)

                self.app.call_from_thread(self._render_dashboard, courses, items, course_grades)
            except Exception as exc:
                err = str(exc)
                self.app.call_from_thread(lambda: self.scores_panel.update(f"[red]Error: {err}[/red]"))
            finally:
                self._loading = False

        threading.Thread(target=worker, daemon=True).start()

    def _render_dashboard(
        self,
        courses: dict[int, tuple[str, str]],
        items: list[CanvasItem],
        course_grades: dict[int, list[dict[str, Any]]],
    ) -> None:
        tz = self._owner.cfg.user_tz
        now = dt.datetime.now(ZoneInfo(tz))

        # ── Scores bar chart (top-right) ──
        bar_entries: list[BarEntry] = []
        course_sparklines: dict[str, list[float]] = {}
        course_completion: list[tuple[str, int, int]] = []

        for cid, (code, _name) in sorted(courses.items(), key=lambda kv: kv[1][0]):
            grades = course_grades.get(cid, [])
            total_score = 0.0
            total_possible = 0.0
            graded_count = 0
            total_count = 0
            pcts: list[float] = []

            for a in grades:
                pts = a.get("points_possible")
                sub = a.get("submission") or {}
                score = sub.get("score")
                total_count += 1

                if score is not None and pts:
                    total_score += float(score)
                    total_possible += float(pts)
                    graded_count += 1
                    pcts.append(100.0 * float(score) / float(pts))

            avg = (100.0 * total_score / total_possible) if total_possible > 0 else 0.0
            bar_entries.append(BarEntry(label=code, value=avg, suffix=f"{avg:.1f}%"))
            if pcts:
                course_sparklines[code] = pcts
            course_completion.append((code, graded_count, total_count))

        if bar_entries:
            scores_text = render_bar_chart(bar_entries, bar_width=25, title="Course Scores")
        else:
            scores_text = "[bold]Course Scores[/bold]\n[dim]No active course score data yet[/dim]"
        self.scores_panel.update(scores_text)

        # ── Due soon panel (middle-left) ──
        upcoming: list[tuple[str, CanvasItem]] = []
        overdue_count = 0
        for it in items:
            if "submitted" in it.status_flags:
                continue
            if not it.due_iso:
                continue
            try:
                due = dt.datetime.fromisoformat(it.due_iso.replace("Z", "+00:00"))
                delta_h = (due - now.astimezone(dt.UTC)).total_seconds() / 3600.0
            except Exception:
                continue

            if delta_h < 0:
                overdue_count += 1
                upcoming.append(("[red]OVERDUE[/red]", it))
            elif delta_h < 6:
                upcoming.append(("[red]< 6h[/red]", it))
            elif delta_h < 12:
                upcoming.append(("[yellow]< 12h[/yellow]", it))
            elif delta_h < 24:
                upcoming.append(("[green]today[/green]", it))
            elif delta_h < 48:
                upcoming.append(("[cyan]< 48h[/cyan]", it))

        # Sort by due date
        upcoming.sort(key=lambda t: t[1].due_iso)

        border_color = urgency_color(len(upcoming))
        due_lines = [f"[bold {border_color}]Due Soon ({len(upcoming)} items)[/bold {border_color}]"]
        if not upcoming:
            due_lines.append("[green]  Nothing due in the next 48 hours! [/green]")
        else:
            for urgency, it in upcoming[:12]:
                title = it.title[:40]
                due_lines.append(f"  {urgency}  [{grade_color(50)}]{it.course_code}[/{grade_color(50)}] {title}")
            if len(upcoming) > 12:
                due_lines.append(f"  [dim]… and {len(upcoming) - 12} more[/dim]")
        if overdue_count:
            due_lines.append(f"\n  [red bold]!! {overdue_count} overdue item(s)[/red bold]")

        self.due_panel.update("\n".join(due_lines))

        # ── Completion gauges (middle-right) ──
        gauge_lines = ["[bold]Assignment Completion[/bold]"]
        if not course_completion:
            gauge_lines.append("[dim]No course grade data loaded yet[/dim]")
        else:
            for code, done, total in course_completion:
                gauge_lines.append(render_gauge(done, total, width=18, label=code))
        self.completion_panel.update("\n".join(gauge_lines))

        # ── Grade trends (bottom) ──
        series_list: list[PlotSeries] = []
        colors = ["cyan", "green", "yellow", "magenta", "blue", "red"]
        for i, (code, pcts) in enumerate(course_sparklines.items()):
            if pcts:
                series_list.append(
                    PlotSeries(
                        values=pcts[-20:],
                        color=colors[i % len(colors)],
                        label=f"{code} {sparkline(pcts[-10:], colors[i % len(colors)])}",
                    )
                )

        if series_list:
            plot_text = render_braille_plot(
                series_list,
                width=50,
                height=6,
                title="Grade Trends (recent assignments)",
                y_min=0,
                y_max=100,
            )
            self.trends_panel.update(plot_text)
        else:
            self.trends_panel.update("[dim]No grade data for trends[/dim]")

    def action_refresh_dash(self) -> None:
        self._load_dashboard()

    def action_back_to_main(self) -> None:
        self.app.pop_screen()

    def action_pop(self) -> None:
        self.app.pop_screen()
