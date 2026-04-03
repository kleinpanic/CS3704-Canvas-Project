"""Course management screen — show/hide courses, auto-detect ghost courses.

Lets any user manage which courses appear in all views (table, graphs,
trends, score bars). Ghost courses (old semesters, advising entries,
0-assignment courses) are auto-detected and can be hidden in one click.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

if TYPE_CHECKING:
    from ..app import CanvasTUI


# Patterns that suggest a course is not a real class
_GHOST_PATTERNS = [
    r"advising",
    r"orientation",
    r"lockdown\s*browser",
    r"makeup\s*test",
    r"IFC\s+\d{4}",
    r"^CSVC$",
    r"follow[\s-]*up",
    r"tutorial",
    r"training",
    r"sandbox",
    r"test\s*course",
]
_GHOST_RE = re.compile("|".join(_GHOST_PATTERNS), re.IGNORECASE)


def is_likely_ghost(
    code: str,
    name: str,
    assignment_count: int = 0,
    current_term: str = "",
) -> tuple[bool, str]:
    """Detect if a course is likely a ghost/junk course.

    Returns (is_ghost, reason).
    """
    full = f"{code} {name}"

    # Pattern match against known ghost indicators
    m = _GHOST_RE.search(full)
    if m:
        return True, f"matches '{m.group()}'"

    # Old semester detection (year < current year or >1 year old)
    year_match = re.search(r"(20\d{2})", full)
    if year_match:
        import datetime as dt
        year = int(year_match.group(1))
        now_year = dt.datetime.now().year
        if year < now_year - 1:
            return True, f"old semester ({year})"

    # Zero assignments and no grade data
    if assignment_count == 0:
        return True, "0 assignments"

    return False, ""


class CourseManagerScreen(Screen):
    """Manage course visibility — hide ghost courses from all views."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("enter", "toggle", "Show/Hide"),
        ("space", "toggle", "Show/Hide"),
        ("a", "auto_detect", "Auto-hide ghosts"),
        ("s", "show_all", "Show all"),
    ]

    def __init__(self, owner_app: CanvasTUI) -> None:
        super().__init__()
        self._owner = owner_app

    def compose(self) -> ComposeResult:
        with Vertical(id="cm-root"):
            self.header = Static(id="cm-header")
            yield self.header
            self.course_table = DataTable(id="cm-table", zebra_stripes=True)
            yield self.course_table
            self.status = Static(id="cm-status")
            yield self.status
            yield Footer()

    def on_mount(self) -> None:
        self.header.update(
            "[bold]Course Manager[/bold]\n"
            "[dim]Enter/Space = toggle  |  a = auto-hide ghosts  |  s = show all  |  Esc = back[/dim]"
        )
        self.course_table.add_columns("Visible", "Code", "Name", "Items", "Score", "Ghost?")
        self.course_table.cursor_type = "row"
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.course_table.clear()
        hidden = self._owner.state.get_hidden_courses()
        courses = self._owner.course_cache

        for cid, (code, name) in sorted(courses.items(), key=lambda kv: kv[1][0]):
            is_hidden = cid in hidden

            # Count assignments
            item_count = sum(1 for it in self._owner.items if it.course_id == cid)

            # Get score
            grades = self._owner._grade_cache.get(cid, [])
            ts, tp = 0.0, 0.0
            for a in grades:
                pts = a.get("points_possible")
                sub = a.get("submission") or {}
                sc = sub.get("score")
                if sc is not None and pts:
                    ts += float(sc)
                    tp += float(pts)
            avg = f"{100.0 * ts / tp:.0f}%" if tp > 0 else "---"

            # Ghost detection
            ghost, reason = is_likely_ghost(code, name, item_count)
            ghost_str = f"[yellow]{reason}[/yellow]" if ghost else ""

            vis_str = "[green]YES[/green]" if not is_hidden else "[red]HIDDEN[/red]"

            self.course_table.add_row(
                vis_str, code, name[:40], str(item_count), avg, ghost_str
            )

        hidden_count = len(hidden)
        total = len(courses)
        self.status.update(
            f"[dim]{total} courses total, {hidden_count} hidden, "
            f"{total - hidden_count} visible[/dim]"
        )

    def _get_selected_course_id(self) -> int | None:
        if self.course_table.cursor_row is None:
            return None
        courses_sorted = sorted(self._owner.course_cache.items(), key=lambda kv: kv[1][0])
        idx = self.course_table.cursor_row
        if 0 <= idx < len(courses_sorted):
            return courses_sorted[idx][0]
        return None

    def action_toggle(self) -> None:
        cid = self._get_selected_course_id()
        if cid is not None:
            new_hidden = self._owner.state.toggle_course_hidden(cid)
            code = self._owner.course_cache.get(cid, ("?", "?"))[0]
            action = "hidden" if new_hidden else "shown"
            self._refresh_table()
            self.status.update(f"[bold]{code}[/bold] {action}")

    def action_auto_detect(self) -> None:
        """Auto-hide all detected ghost courses."""
        hidden = self._owner.state.get_hidden_courses()
        count = 0
        for cid, (code, name) in self._owner.course_cache.items():
            item_count = sum(1 for it in self._owner.items if it.course_id == cid)
            ghost, _reason = is_likely_ghost(code, name, item_count)
            if ghost and cid not in hidden:
                hidden.append(cid)
                count += 1
        self._owner.state.set_hidden_courses(hidden)
        self._refresh_table()
        self.status.update(f"[bold]Auto-hidden {count} ghost course(s)[/bold]")

    def action_show_all(self) -> None:
        """Unhide all courses."""
        self._owner.state.set_hidden_courses([])
        self._refresh_table()
        self.status.update("[bold]All courses visible[/bold]")

    def action_pop(self) -> None:
        self.dismiss()

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.dismiss()
