"""Paginated command bar — shows keybindings in groups, cycled with [ and ]."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static

# Binding groups shown one page at a time
PAGES: list[tuple[str, list[tuple[str, str]]]] = [
    ("Navigation", [
        ("q", "Quit"),
        ("r", "Refresh"),
        ("o", "Open"),
        ("Enter", "Details"),
        ("d", "Preview"),
        ("/", "Filter"),
        ("s", "Sort"),
        ("?", "Help"),
    ]),
    ("Views", [
        ("D", "Dashboard"),
        ("V", "Analytics"),
        ("M", "Courses"),
        ("G", "Grades"),
        ("S", "Syllabi"),
        ("A", "Announce"),
        ("F", "Files"),
        ("W", "Week"),
    ]),
    ("Actions", [
        ("y", "Copy URL"),
        ("w", "Download"),
        ("c", "ICS"),
        ("C", "ICS+cal"),
        ("g", "Course"),
        ("x", "Hide"),
        ("H", "ShowHid"),
        ("T", "Theme"),
    ]),
    ("Pomodoro", [
        ("1", "30min"),
        ("2", "1hr"),
        ("3", "2hr"),
        ("P", "Custom"),
        ("p", "Pause"),
        ("0", "Stop"),
    ]),
]


class CommandBar(Static):
    """Paginated footer showing keybindings in groups."""

    page: reactive[int] = reactive(0)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._max_page = len(PAGES) - 1

    def render(self) -> str:
        pg_name, bindings = PAGES[self.page]
        parts = [f"[bold]{pg_name}[/bold]"]
        for key, label in bindings:
            parts.append(f" [cyan]{key}[/cyan]={label}")
        nav = f"  [dim][/] pg {self.page + 1}/{self._max_page + 1}[/dim]"
        return "".join(parts) + nav

    def next_page(self) -> None:
        self.page = (self.page + 1) % (self._max_page + 1)

    def prev_page(self) -> None:
        self.page = (self.page - 1) % (self._max_page + 1)

    def watch_page(self, _old: int, _new: int) -> None:
        self.refresh()
