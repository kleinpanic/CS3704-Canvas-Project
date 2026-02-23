"""Calendar week view — items displayed in a 7-day grid."""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..models import CanvasItem
from ..utils import local_dt

if TYPE_CHECKING:
    from ..app import CanvasTUI


class WeekViewScreen(Screen):
    """7-day calendar grid showing items by due date."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("left", "prev_week", "← Prev week"),
        ("right", "next_week", "→ Next week"),
        ("t", "this_week", "Today"),
    ]

    def __init__(self, owner_app: CanvasTUI, items: list[CanvasItem]) -> None:
        super().__init__()
        self._owner = owner_app
        self._items = items
        self._tz = owner_app.cfg.user_tz
        self._week_start = _monday_of(dt.datetime.now(ZoneInfo(self._tz)).date())
        self._day_cells: list[Static] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="week-root"):
            self.week_label = Static(id="week-label")
            yield self.week_label
            with Grid(id="week-grid"):
                for i in range(7):
                    cell = Static(id=f"day-{i}", classes="day-cell")
                    self._day_cells.append(cell)
                    yield cell
            yield Footer()

    def on_mount(self) -> None:
        self._render_week()

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def _render_week(self) -> None:
        ws = self._week_start
        we = ws + dt.timedelta(days=6)
        self.week_label.update(
            f"[b]Week of {ws.strftime('%b %d')} — {we.strftime('%b %d, %Y')}[/b]  "
            f"[dim](← → to navigate, t for today)[/dim]"
        )

        # Bucket items by day
        day_items: dict[int, list[CanvasItem]] = {i: [] for i in range(7)}
        today = dt.datetime.now(ZoneInfo(self._tz)).date()

        for it in self._items:
            if not it.due_iso:
                continue
            try:
                due_date = local_dt(it.due_iso, self._tz).date()
            except Exception:
                continue
            offset = (due_date - ws).days
            if 0 <= offset < 7:
                day_items[offset].append(it)

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i in range(7):
            day = ws + dt.timedelta(days=i)
            is_today = day == today
            header_style = "[bold cyan]" if is_today else "[bold]"
            end_style = "[/bold cyan]" if is_today else "[/bold]"

            header = f"{header_style}{day_names[i]} {day.strftime('%m/%d')}{end_style}"
            if is_today:
                header += " ◄"

            items_in_day = day_items[i]
            if not items_in_day:
                body = "[dim]  (nothing)[/dim]"
            else:
                lines = []
                for it in items_in_day[:8]:  # Cap at 8 per day
                    color = _urgency_color(it, self._tz)
                    time_str = ""
                    if it.due_iso:
                        with contextlib.suppress(Exception):
                            time_str = local_dt(it.due_iso, self._tz).strftime("%H:%M")
                    prefix = f"  {time_str} " if time_str else "  "
                    status = ""
                    if "submitted" in it.status_flags:
                        status = " [x]"
                    elif "missing" in it.status_flags:
                        status = " [ ]"
                    lines.append(f"[{color}]{prefix}{it.title[:30]}{status}[/{color}]")
                if len(items_in_day) > 8:
                    lines.append(f"  [dim]+{len(items_in_day) - 8} more[/dim]")
                body = "\n".join(lines)

            self._day_cells[i].update(f"{header}\n{body}")

    def action_prev_week(self) -> None:
        self._week_start -= dt.timedelta(days=7)
        self._render_week()

    def action_next_week(self) -> None:
        self._week_start += dt.timedelta(days=7)
        self._render_week()

    def action_this_week(self) -> None:
        self._week_start = _monday_of(dt.datetime.now(ZoneInfo(self._tz)).date())
        self._render_week()

    def action_pop(self) -> None:
        self.app.pop_screen()


def _monday_of(d: dt.date) -> dt.date:
    """Get the Monday of the week containing date d."""
    return d - dt.timedelta(days=d.weekday())


def _urgency_color(it: CanvasItem, tz: str) -> str:
    """Color based on due urgency."""
    if "submitted" in it.status_flags:
        return "green"
    if not it.due_iso:
        return "white"
    try:
        now = dt.datetime.now(ZoneInfo(tz))
        due = local_dt(it.due_iso, tz)
        delta_h = (due - now).total_seconds() / 3600.0
    except Exception:
        return "white"
    if delta_h < 0:
        return "red"
    if delta_h <= 8:
        return "orange1"
    if delta_h <= 24:
        return "yellow"
    return "white"
