"""Grades screen — per-course grade breakdown with averages."""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from ..widgets.plots import (
    WeightSegment,
    render_gauge,
    render_weight_bar,
)

if TYPE_CHECKING:
    from ..app import CanvasTUI


class GradesScreen(Screen):
    """Grades overview — course list + assignment grades with averages."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("enter", "select_course", "View grades"),
        ("r", "refresh_grades", "Refresh"),
    ]

    def __init__(self, owner_app: CanvasTUI, courses: dict[int, tuple[str, str]]) -> None:
        super().__init__()
        self._owner = owner_app
        self.courses = courses
        self._row_to_cid: list[int] = []
        self._course_grades: dict[int, list[dict[str, Any]]] = {}
        self._loading = False

    def compose(self) -> ComposeResult:
        with Vertical(id="grades-root"):
            with Horizontal(id="grades-split"):
                self.course_table = DataTable(zebra_stripes=True, id="grades-courses")
                yield self.course_table
                with Vertical(id="grades-detail"):
                    self.summary = Static(id="grades-summary")
                    yield self.summary
                    self.grade_table = DataTable(zebra_stripes=True, id="grades-table")
                    yield self.grade_table
            yield Footer()

    def on_mount(self) -> None:
        self.course_table.clear(columns=True)
        self.course_table.add_columns("Course", "Avg")
        self.course_table.cursor_type = "row"
        self._row_to_cid.clear()

        for cid, (code, _name) in sorted(self.courses.items(), key=lambda kv: (kv[1][0], kv[0])):
            self.course_table.add_row(f"{code}", "-")
            self._row_to_cid.append(cid)

        with contextlib.suppress(Exception):
            self.course_table.cursor_coordinate = (0, 0)

        self.grade_table.clear(columns=True)
        self.grade_table.add_columns("Assignment", "Score", "Points", "%", "Status")
        self.grade_table.cursor_type = "row"

        self.summary.update("[dim]Select a course to view grades[/dim]")

        # Auto-load first course
        cid = self._selected_course()
        if cid is not None:
            self._load_grades(cid)

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def _selected_course(self) -> int | None:
        row = self.course_table.cursor_row
        if row is not None and 0 <= row < len(self._row_to_cid):
            return self._row_to_cid[row]
        return None

    def on_data_table_cursor_moved(self, event: Any) -> None:
        src = getattr(event, "data_table", None) or getattr(event, "control", None)
        if src is not self.course_table:
            return
        cid = self._selected_course()
        if cid is not None:
            self._load_grades(cid)

    def _load_grades(self, cid: int) -> None:
        if self._loading:
            return
        self._loading = True
        self.summary.update("[dim]Loading grades…[/dim]")

        def worker() -> None:
            try:
                if cid in self._course_grades:
                    grades = self._course_grades[cid]
                else:
                    grades = self._owner.api.fetch_grades(cid)
                    self._course_grades[cid] = grades
                self.app.call_from_thread(self._render_grades, cid, grades)
            except Exception as exc:
                err = str(exc)
                self.app.call_from_thread(lambda: self.summary.update(f"[red]Error: {err}[/red]"))
            finally:
                self._loading = False

        threading.Thread(target=worker, daemon=True).start()

    def _render_grades(self, cid: int, assignments: list[dict[str, Any]]) -> None:
        code, name = self.courses.get(cid, ("?", "?"))
        self.grade_table.clear()

        graded = []
        ungraded = []
        total_score = 0.0
        total_possible = 0.0

        for a in assignments:
            aname = a.get("name") or "(untitled)"
            pts = a.get("points_possible")
            sub = a.get("submission") or {}
            score = sub.get("score")
            workflow = sub.get("workflow_state") or ""

            status_parts: list[str] = []
            if sub.get("excused"):
                status_parts.append("excused")
            elif score is not None:
                status_parts.append("graded")
                graded.append((aname, float(score), float(pts or 0)))
                if pts:
                    total_score += float(score)
                    total_possible += float(pts)
            elif workflow == "submitted":
                status_parts.append("submitted")
                ungraded.append(aname)
            elif sub.get("missing"):
                status_parts.append("[red]missing[/red]")
            else:
                status_parts.append("pending")
                ungraded.append(aname)

            if sub.get("late"):
                status_parts.append("[yellow]late[/yellow]")

            score_str = f"{float(score):.1f}" if score is not None else "-"
            pts_str = f"{float(pts):.1f}" if pts else "-"
            pct_str = ""
            if score is not None and pts:
                pct = 100.0 * float(score) / float(pts)
                color = "green" if pct >= 90 else "yellow" if pct >= 70 else "red"
                pct_str = f"[{color}]{pct:.1f}%[/{color}]"

            status = ", ".join(status_parts) or "-"
            self.grade_table.add_row(aname[:50], score_str, pts_str, pct_str, status)

        # Summary
        avg = (100.0 * total_score / total_possible) if total_possible > 0 else 0.0
        avg_color = "green" if avg >= 90 else "yellow" if avg >= 70 else "red"

        # Sparkline of recent grades
        recent_pcts = []
        for _, sc, pt in graded[-10:]:
            if pt > 0:
                recent_pcts.append(sc / pt)
        spark = _sparkline(recent_pcts) if recent_pcts else ""

        # Completion gauge
        gauge = render_gauge(len(graded), len(graded) + len(ungraded), width=20)

        summary_text = (
            f"[b]{code} — {name}[/b]\n"
            f"Average: [{avg_color}]{avg:.1f}%[/{avg_color}]  "
            f"({len(graded)} graded, {len(ungraded)} pending)\n"
            f"Total: {total_score:.1f} / {total_possible:.1f}\n"
            f"Progress: {gauge}\n"
        )
        if spark:
            summary_text += f"Trend: {spark}\n"

        # Fetch and render assignment group weights
        groups = self._owner.api.fetch_assignment_groups(cid)
        if groups:
            segments = [
                WeightSegment(label=g.get("name", "?"), weight=g.get("group_weight", 0))
                for g in groups if g.get("group_weight", 0) > 0
            ]
            if segments:
                summary_text += "\n" + render_weight_bar(segments, width=28, title="Grade Weights")

        self.summary.update(summary_text)

        # Update course list avg column
        row_idx = None
        for i, c in enumerate(self._row_to_cid):
            if c == cid:
                row_idx = i
                break
        if row_idx is not None:
            with contextlib.suppress(Exception):
                self.course_table.update_cell_at(
                    (row_idx, 1), f"[{avg_color}]{avg:.1f}%[/{avg_color}]"
                )

    def action_select_course(self) -> None:
        cid = self._selected_course()
        if cid is not None:
            self._load_grades(cid)

    def action_refresh_grades(self) -> None:
        self._course_grades.clear()
        cid = self._selected_course()
        if cid is not None:
            self._load_grades(cid)

    def action_pop(self) -> None:
        self.app.pop_screen()


def _sparkline(values: list[float]) -> str:
    """Render a sparkline from 0-1 values."""
    chars = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    parts = []
    for v in values:
        v = max(0.0, min(1.0, v))
        idx = int(v * (len(chars) - 1))
        parts.append(chars[idx])
    return "".join(parts)
