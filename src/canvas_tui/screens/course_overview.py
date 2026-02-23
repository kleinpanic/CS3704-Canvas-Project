"""Course overview screen — deep-dive into a single course.

Inspired by GideonWolfe/canvas-tui's courseOverview.go:
- Course info header (instructor, term, enrollment)
- Assignment completion gauge
- Recent scores table with color grading
- Upcoming assignments for this course
- Grade trend plot
- Assignment group weight breakdown
"""

from __future__ import annotations

import datetime as dt
import threading
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..widgets.plots import (
    BarEntry,
    PlotSeries,
    WeightSegment,
    grade_color,
    render_bar_chart,
    render_braille_plot,
    render_gauge,
    render_weight_bar,
)

if TYPE_CHECKING:
    from ..app import CanvasTUI


class CourseOverviewScreen(Screen):
    """Detailed view for a single course."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("r", "refresh_course", "Refresh"),
    ]

    def __init__(self, owner_app: CanvasTUI, course_id: int, code: str, name: str) -> None:
        super().__init__()
        self._owner = owner_app
        self._course_id = course_id
        self._code = code
        self._name = name
        self._loading = False

    def compose(self) -> ComposeResult:
        with Vertical(id="co-root"):
            self.header_panel = Static(id="co-header")
            yield self.header_panel
            with Horizontal(id="co-body"):
                with Vertical(id="co-left"):
                    self.upcoming_panel = Static(id="co-upcoming")
                    yield self.upcoming_panel
                    self.scores_panel = Static(id="co-scores")
                    yield self.scores_panel
                with Vertical(id="co-right"):
                    self.gauge_panel = Static(id="co-gauge")
                    yield self.gauge_panel
                    self.weights_panel = Static(id="co-weights")
                    yield self.weights_panel
                    self.trend_panel = Static(id="co-trend")
                    yield self.trend_panel
            yield Footer()

    def on_mount(self) -> None:
        self.header_panel.update(f"[bold cyan]{self._code}[/bold cyan] — {self._name}\n[dim]Loading…[/dim]")
        self._load_course()

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def _load_course(self) -> None:
        if self._loading:
            return
        self._loading = True

        def worker() -> None:
            try:
                cid = self._course_id
                api = self._owner.api

                # Fetch grades + assignment groups in parallel-ish
                grades = api.fetch_grades(cid)
                groups = api.fetch_assignment_groups(cid)
                course_info = api.fetch_course_info(cid)

                # Items for this course
                course_items = [
                    it for it in self._owner.items
                    if it.course_id == cid
                ]

                self.app.call_from_thread(
                    self._render_course, grades, groups, course_info, course_items
                )
            except Exception as exc:
                err = str(exc)
                self.app.call_from_thread(
                    lambda: self.header_panel.update(f"[red]Error: {err}[/red]")
                )
            finally:
                self._loading = False

        threading.Thread(target=worker, daemon=True).start()

    def _render_course(
        self,
        grades: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        course_info: dict[str, Any] | None,
        course_items: list[CanvasItem],
    ) -> None:
        tz = self._owner.cfg.user_tz
        dt.datetime.now(ZoneInfo(tz))

        # ── Header with course info ──
        header_parts = [f"[bold cyan]{self._code}[/bold cyan] — {self._name}"]
        if course_info:
            # Instructor
            teachers = course_info.get("teachers") or []
            if teachers:
                names = ", ".join(t.get("display_name", "?") for t in teachers)
                header_parts.append(f"[dim]Instructor:[/dim] {names}")
            # Term
            term = course_info.get("term") or {}
            if term.get("name"):
                header_parts.append(f"[dim]Term:[/dim] {term['name']}")
            # Students
            students = course_info.get("total_students")
            if students is not None:
                header_parts.append(f"[dim]Students:[/dim] {students}")
        self.header_panel.update("\n".join(header_parts))

        # ── Upcoming assignments for this course ──
        upcoming_lines = ["[bold]Upcoming[/bold]"]
        upcoming = [
            it for it in course_items
            if "submitted" not in it.status_flags and it.due_iso
        ]
        upcoming.sort(key=lambda it: it.due_iso)
        if not upcoming:
            upcoming_lines.append("  [green]Nothing upcoming! 🎉[/green]")
        else:
            for it in upcoming[:8]:
                title = it.title[:45]
                upcoming_lines.append(f"  [dim]{it.due_rel:>8}[/dim]  {title}")
            if len(upcoming) > 8:
                upcoming_lines.append(f"  [dim]… +{len(upcoming) - 8} more[/dim]")
        self.upcoming_panel.update("\n".join(upcoming_lines))

        # ── Recent scores ──
        score_entries: list[BarEntry] = []
        graded_count = 0
        total_count = len(grades)
        total_score = 0.0
        total_possible = 0.0
        pcts: list[float] = []

        for a in grades:
            pts = a.get("points_possible")
            sub = a.get("submission") or {}
            score = sub.get("score")
            aname = (a.get("name") or "?")[:30]
            total_count = total_count  # just for clarity

            if score is not None and pts:
                graded_count += 1
                pct = 100.0 * float(score) / float(pts)
                total_score += float(score)
                total_possible += float(pts)
                pcts.append(pct)
                score_entries.append(BarEntry(
                    label=aname,
                    value=pct,
                    suffix=f"{float(score):.0f}/{float(pts):.0f} ({pct:.0f}%)",
                ))

        # Show last 8 graded
        recent = score_entries[-8:] if len(score_entries) > 8 else score_entries
        scores_text = render_bar_chart(recent, bar_width=15, title="Recent Scores")
        self.scores_panel.update(scores_text)

        # ── Completion gauge ──
        avg = (100.0 * total_score / total_possible) if total_possible > 0 else 0.0
        avg_color = grade_color(avg)
        gauge_text = (
            f"[bold]Progress[/bold]\n"
            f"{render_gauge(graded_count, total_count, width=22)}\n\n"
            f"  Course Average: [{avg_color}][bold]{avg:.1f}%[/bold][/{avg_color}]\n"
            f"  Total: {total_score:.0f} / {total_possible:.0f}"
        )
        self.gauge_panel.update(gauge_text)

        # ── Assignment group weights ──
        if groups:
            segments: list[WeightSegment] = []
            for g in groups:
                w = g.get("group_weight", 0)
                gname = g.get("name") or "?"
                if w > 0:
                    segments.append(WeightSegment(label=gname, weight=w))
            weights_text = render_weight_bar(segments, width=30, title="Grade Weights")
        else:
            weights_text = "[dim]No weight data available[/dim]"
        self.weights_panel.update(weights_text)

        # ── Grade trend plot ──
        if pcts:
            series = [PlotSeries(values=pcts[-20:], color="cyan", label=self._code)]
            trend_text = render_braille_plot(
                series, width=35, height=5,
                title="Score Trend", y_min=0, y_max=100,
            )
        else:
            trend_text = "[dim]No graded assignments yet[/dim]"
        self.trend_panel.update(trend_text)

    def action_refresh_course(self) -> None:
        self._load_course()

    def action_pop(self) -> None:
        self.app.pop_screen()


# Avoid circular import — only used for type hint in _render_course
from ..models import CanvasItem  # noqa: E402
