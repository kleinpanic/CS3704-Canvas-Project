"""Grades screen — per-course grade breakdown with trend charts and what-if calculator."""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key, Resize
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from ..screens.modals import InputPrompt
from ..widgets.plots import (
    WeightSegment,
    grade_color,
    render_gauge,
    render_weight_bar,
    sparkline,
)

if TYPE_CHECKING:
    from ..app import CanvasTUI

# Cycle order for sort modes
_SORT_MODES = ["Default", "Score ↓", "% ↓", "Name"]


# ─── Grade summary dataclass (pure, testable) ────────────────────────────────

@dataclass
class GradeSummary:
    """Computed grade summary for a single course."""

    avg: float  # Canvas-authoritative or manual average (0-100)
    projected_avg: float  # avg with what-if scores applied (0-100)
    total_score: float  # sum of graded scores (no what-if)
    total_possible: float  # sum of graded points possible (no what-if)
    graded: list[tuple[str, float, float]] = field(default_factory=list)  # (name, score, pts)
    ungraded: list[str] = field(default_factory=list)  # names of pending/submitted assignments
    has_whatif: bool = False


def calculate_grade_summary(
    assignments: list[dict[str, Any]],
    whatif_map: dict[str, float],
    canvas_score_override: float | None = None,
) -> GradeSummary:
    """Compute grade summary from raw Canvas assignment data plus optional what-if scores.

    Args:
        assignments: Raw assignment dicts from Canvas API (each may have a 'submission' key).
        whatif_map: Mapping of assignment name → hypothetical score for ungraded assignments.
        canvas_score_override: Canvas-computed current score to use in place of manual average.

    Returns:
        A GradeSummary with actual and projected averages.
    """
    graded: list[tuple[str, float, float]] = []
    ungraded: list[str] = []
    total_score = 0.0
    total_possible = 0.0
    whatif_score = 0.0
    whatif_possible = 0.0
    has_whatif = bool(whatif_map)

    for a in assignments:
        aname = a.get("name") or "(untitled)"
        pts = a.get("points_possible")
        sub = a.get("submission") or {}
        score = sub.get("score")
        workflow = sub.get("workflow_state") or ""
        whatif_val = whatif_map.get(aname)

        if sub.get("excused"):
            continue

        if score is not None:
            graded.append((aname, float(score), float(pts or 0)))
            if pts:
                total_score += float(score)
                total_possible += float(pts)
                whatif_score += float(score)
                whatif_possible += float(pts)
        elif whatif_val is not None:
            # Count as graded for projection purposes only
            if pts:
                whatif_score += whatif_val
                whatif_possible += float(pts)
            if workflow not in ("submitted",) and not sub.get("missing"):
                ungraded.append(aname)
        elif workflow == "submitted":
            ungraded.append(aname)
        elif sub.get("missing"):
            pass  # Missing doesn't go into ungraded pending list
        else:
            ungraded.append(aname)

    manual_avg = (100.0 * total_score / total_possible) if total_possible > 0 else 0.0
    avg = canvas_score_override if canvas_score_override is not None else manual_avg
    projected_avg = (100.0 * whatif_score / whatif_possible) if whatif_possible > 0 else avg

    return GradeSummary(
        avg=avg,
        projected_avg=projected_avg,
        total_score=total_score,
        total_possible=total_possible,
        graded=graded,
        ungraded=ungraded,
        has_whatif=has_whatif,
    )


def sort_assignments(assignments: list[dict[str, Any]], mode: int) -> list[dict[str, Any]]:
    """Return assignments sorted by mode index (0=default, 1=score↓, 2=pct↓, 3=name).

    Args:
        assignments: Raw assignment dicts.
        mode: Sort mode index matching _SORT_MODES.

    Returns:
        A new sorted list (original is not mutated).
    """
    if mode == 0:
        return list(assignments)

    if mode == 1:  # Score ↓ — ungraded to end
        def _key_score(a: dict[str, Any]) -> float:
            sub = a.get("submission") or {}
            s = sub.get("score")
            return -(float(s) if s is not None else -1.0)

        return sorted(assignments, key=_key_score)

    if mode == 2:  # % ↓ — ungraded to end
        def _key_pct(a: dict[str, Any]) -> float:
            sub = a.get("submission") or {}
            s = sub.get("score")
            pts = a.get("points_possible")
            if s is not None and pts:
                return -(float(s) / float(pts))
            return 1.0  # ungraded sorts last

        return sorted(assignments, key=_key_pct)

    if mode == 3:  # Name A-Z
        return sorted(assignments, key=lambda a: (a.get("name") or "").lower())

    return list(assignments)


# ─── Screen ──────────────────────────────────────────────────────────────────

class GradesScreen(Screen):
    """Grades overview — course list, assignment breakdown, trend sparkline, and what-if calculator."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("enter", "select_course", "View grades"),
        ("r", "refresh_grades", "Refresh"),
        ("w", "whatif_prompt", "What-If"),
        ("W", "clear_whatif", "Clear What-If"),
        ("s", "toggle_sort", "Sort"),
    ]

    def __init__(self, owner_app: CanvasTUI, courses: dict[int, tuple[str, str]]) -> None:
        super().__init__()
        self._owner = owner_app
        self.courses = courses
        self._row_to_cid: list[int] = []
        self._course_grades: dict[int, list[dict[str, Any]]] = {}
        self._loading = False
        # what-if: {course_id: {assignment_name: hypothetical_score}}
        self._whatif: dict[int, dict[str, float]] = {}
        self._sort_mode = 0  # index into _SORT_MODES

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

        cid = self._selected_course()
        if cid is not None:
            self._load_grades(cid)

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def on_resize(self, event: Resize) -> None:
        def _deferred() -> None:
            cid = self._selected_course()
            if cid is not None and cid in self._course_grades:
                self._render_grades(cid, self._course_grades[cid])

        self.call_after_refresh(_deferred)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _selected_course(self) -> int | None:
        row = self.course_table.cursor_row
        if row is not None and 0 <= row < len(self._row_to_cid):
            return self._row_to_cid[row]
        return None

    def _selected_assignment(self, cid: int) -> dict[str, Any] | None:
        """Return the assignment dict under the grade_table cursor."""
        row = self.grade_table.cursor_row
        if row is None or row < 0:
            return None
        ordered = sort_assignments(self._course_grades.get(cid, []), self._sort_mode)
        return ordered[row] if row < len(ordered) else None

    # ── Data loading ─────────────────────────────────────────────────────────

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
                if cid not in self._course_grades:
                    # Prefer the app-level pre-fetched cache to avoid redundant requests
                    app_cache: dict[int, list[dict[str, Any]]] = getattr(self._owner, "_grade_cache", {})
                    grades = app_cache.get(cid) or self._owner.api.fetch_grades(cid)
                    self._course_grades[cid] = grades
                self.app.call_from_thread(self._render_grades, cid, self._course_grades[cid])
            except Exception as exc:
                err = str(exc)
                self.app.call_from_thread(lambda: self.summary.update(f"[red]Error loading grades: {err}[/red]"))
            finally:
                self._loading = False

        threading.Thread(target=worker, daemon=True).start()

    # ── Rendering ────────────────────────────────────────────────────────────

    def _summary_content_width(self) -> int:
        """Return usable character width of the grades summary panel."""
        try:
            return max(24, self.summary.size.width - 4)
        except Exception:
            return 40

    def _render_grades(self, cid: int, assignments: list[dict[str, Any]]) -> None:
        code, name = self.courses.get(cid, ("?", "?"))
        whatif_map = self._whatif.get(cid, {})

        # Compute summary (pure function — easy to test)
        canvas_score = self._owner._course_score_cache.get(cid)
        summary = calculate_grade_summary(assignments, whatif_map, canvas_score)

        # Rebuild assignment table in current sort order
        self.grade_table.clear()
        for a in sort_assignments(assignments, self._sort_mode):
            aname = a.get("name") or "(untitled)"
            pts = a.get("points_possible")
            sub = a.get("submission") or {}
            score = sub.get("score")
            whatif_val = whatif_map.get(aname)

            status_parts: list[str] = []
            display_score = score

            if sub.get("excused"):
                status_parts.append("excused")
            elif score is not None:
                status_parts.append("graded")
            elif whatif_val is not None:
                display_score = whatif_val
                status_parts.append("[cyan]what-if[/cyan]")
            elif (sub.get("workflow_state") or "") == "submitted":
                status_parts.append("submitted")
            elif sub.get("missing"):
                status_parts.append("[red]missing[/red]")
            else:
                status_parts.append("pending")

            if sub.get("late"):
                status_parts.append("[yellow]late[/yellow]")

            score_str = f"{float(display_score):.1f}" if display_score is not None else "-"
            pts_str = f"{float(pts):.1f}" if pts else "-"
            pct_str = ""
            if display_score is not None and pts:
                pct = 100.0 * float(display_score) / float(pts)
                if whatif_val is not None and score is None:
                    pct_str = f"[cyan]~{pct:.1f}%[/cyan]"
                else:
                    color = grade_color(pct)
                    pct_str = f"[{color}]{pct:.1f}%[/{color}]"

            self.grade_table.add_row(aname[:50], score_str, pts_str, pct_str, ", ".join(status_parts) or "-")

        # Build summary panel text — widths adapt to the actual panel size
        panel_w = self._summary_content_width()
        gauge_w = max(12, min(panel_w - 22, 40))
        weight_bar_w = max(20, min(panel_w - 4, 60))

        avg_color = grade_color(summary.avg)
        summary_lines: list[str] = [
            f"[b]{code} — {name}[/b]",
            f"Average: [{avg_color}]{summary.avg:.1f}%[/{avg_color}]  "
            f"({len(summary.graded)} graded, {len(summary.ungraded)} pending)",
            f"Total: {summary.total_score:.1f} / {summary.total_possible:.1f}",
            f"Progress: {render_gauge(len(summary.graded), len(summary.graded) + len(summary.ungraded), width=gauge_w)}",
        ]

        # What-if projected grade line
        if not summary.has_whatif:
            summary_lines.append(
                f"[dim]Press [w] on an ungraded row to try what-if scores[/dim]"
            )
        else:
            proj_color = grade_color(summary.projected_avg)
            summary_lines.append(
                f"[bold cyan]⟳ WHAT-IF[/bold cyan]  "
                f"Projected: [{proj_color}]{summary.projected_avg:.1f}%[/{proj_color}]  "
                f"[dim]([W] to clear)[/dim]"
            )

        # Trend sparkline from recent 10 graded assignments (% values)
        recent_pcts = [sc / pt * 100 for _, sc, pt in summary.graded[-10:] if pt > 0]
        if recent_pcts:
            spark = sparkline(recent_pcts)
            summary_lines.append(f"Trend: {spark}")

        # Sort mode hint
        summary_lines.append(
            f"[dim]Sort: {_SORT_MODES[self._sort_mode]}  "
            f"[s] cycle  [w] what-if  [r] refresh[/dim]"
        )

        # Assignment group weight bar
        groups = self._owner.api.fetch_assignment_groups(cid)
        if groups:
            segments = [
                WeightSegment(label=g.get("name", "?"), weight=g.get("group_weight", 0))
                for g in groups
                if g.get("group_weight", 0) > 0
            ]
            if segments:
                summary_lines.append("\n" + render_weight_bar(segments, width=weight_bar_w, title="Grade Weights"))

        self.summary.update("\n".join(summary_lines))

        # Update the course list Avg column
        for i, c in enumerate(self._row_to_cid):
            if c == cid:
                with contextlib.suppress(Exception):
                    self.course_table.update_cell_at((i, 1), f"[{avg_color}]{summary.avg:.1f}%[/{avg_color}]")
                break

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_select_course(self) -> None:
        cid = self._selected_course()
        if cid is not None:
            self._load_grades(cid)

    def action_refresh_grades(self) -> None:
        self._course_grades.clear()
        cid = self._selected_course()
        if cid is not None:
            self._load_grades(cid)

    def action_toggle_sort(self) -> None:
        """Cycle through sort modes and re-render the current course."""
        self._sort_mode = (self._sort_mode + 1) % len(_SORT_MODES)
        cid = self._selected_course()
        if cid is not None and cid in self._course_grades:
            self._render_grades(cid, self._course_grades[cid])

    def action_whatif_prompt(self) -> None:
        """Open an input prompt to enter a hypothetical score for the selected assignment."""
        cid = self._selected_course()
        if cid is None:
            return
        if not self._course_grades.get(cid):
            return

        a = self._selected_assignment(cid)
        if a is None:
            return

        aname = a.get("name") or "(untitled)"
        pts = a.get("points_possible")
        sub = a.get("submission") or {}
        real_score = sub.get("score")

        if real_score is not None:
            self.summary.update(
                f"[yellow]'{aname[:40]}' already has a real grade ({real_score:.1f} pts).\n"
                "Select an ungraded assignment for what-if.[/yellow]"
            )
            return

        pts_display = f"{float(pts):.1f}" if pts else "?"
        existing_val: float | None = self._whatif.get(cid, {}).get(aname)
        default_str = f"{existing_val:.1f}" if existing_val is not None else ""

        def _apply(val: str) -> None:
            if not val:
                return
            try:
                score_val = float(val)
            except ValueError:
                return
            # Cap at points possible to prevent impossible scores
            if pts and score_val > float(pts):
                score_val = float(pts)
            score_val = max(0.0, score_val)
            if cid not in self._whatif:
                self._whatif[cid] = {}
            self._whatif[cid][aname] = score_val
            if cid in self._course_grades:
                self._render_grades(cid, self._course_grades[cid])

        modal = InputPrompt(
            title=f"What-If Score: {aname[:45]}\nEnter hypothetical score (0 - {pts_display} pts):",
            placeholder=f"e.g. {int(float(pts) * 0.85) if pts else 85}",
            default=default_str,
        )
        self.app.push_screen(modal, callback=_apply)

    def action_clear_whatif(self) -> None:
        """Clear all what-if scores for the current course and re-render."""
        cid = self._selected_course()
        if cid is None:
            return
        self._whatif.pop(cid, None)
        if cid in self._course_grades:
            self._render_grades(cid, self._course_grades[cid])

    def action_pop(self) -> None:
        self.app.pop_screen()
