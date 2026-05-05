"""Settings screen — theme, layout, keybindings, and data preferences."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Select, Static

if TYPE_CHECKING:
    from ..app import CanvasTUI

# Actions that can have extra keybinding aliases added via the settings screen.
# These map 1-to-1 with action_<name>() methods on CanvasTUI.
REBINDABLE_ACTIONS: list[str] = [
    "quit",
    "refresh",
    "open",
    "open_details",
    "quick_preview",
    "filter",
    "toggle_hide",
    "toggle_show_hidden",
    "cycle_sort",
    "toggle_theme",
    "open_syllabi",
    "open_announcements",
    "open_grades",
    "open_files",
    "open_week",
    "open_dashboard",
    "open_analytics",
    "manage_courses",
    "show_help",
    "open_settings",
]

_SECTION_CSS = """
SettingsScreen {
    background: $surface;
}
#set-title {
    dock: top;
    height: 3;
    padding: 1 2;
    background: $primary;
    color: $text;
    text-style: bold;
}
#set-scroll {
    height: 1fr;
    padding: 0 2;
}
.set-section-hdr {
    margin-top: 1;
    padding: 0 0 0 0;
    color: $accent;
    text-style: bold;
}
.set-help {
    color: $text-muted;
}
Label {
    margin-top: 1;
}
Input {
    margin-bottom: 0;
}
Select {
    margin-bottom: 0;
}
#set-conflict-msg {
    margin-top: 1;
    min-height: 1;
}
#set-buttons {
    dock: bottom;
    height: 3;
    padding: 0 2;
    align: right middle;
}
#set-save {
    margin-right: 1;
}
"""


def _find_conflicts(keybindings: dict[str, str]) -> str:
    """Return a description of any key used for multiple actions, or empty string."""
    seen: dict[str, str] = {}
    for action, key in keybindings.items():
        if not key:
            continue
        if key in seen:
            return f"'{key}' is mapped to both '{seen[key]}' and '{action}'"
        seen[key] = action
    return ""


class SettingsScreen(Screen[dict[str, Any] | None]):
    """Full-screen configuration form.

    Dismissed with a dict of new values on Save, or None on Cancel.
    """

    CSS = _SECTION_CSS

    BINDINGS = [
        ("escape", "close", "Cancel"),
        ("ctrl+s", "save", "Save & Apply"),
    ]

    def __init__(self, owner_app: CanvasTUI) -> None:
        super().__init__()
        self._owner = owner_app

    def compose(self) -> ComposeResult:
        cfg = self._owner.cfg

        yield Static("⚙  Settings", id="set-title")

        with ScrollableContainer(id="set-scroll"):
            # ── Appearance ──────────────────────────────────────────────
            yield Static("Appearance", classes="set-section-hdr")

            yield Label("Theme")
            yield Select(
                [("Dark", "dark"), ("Light", "light")],
                value=cfg.theme,
                id="set-theme",
            )

            yield Label("Sidebar position  (applies on restart)")
            yield Select(
                [("Right (default)", "right"), ("Left", "left")],
                value=cfg.sidebar_position,
                id="set-sidebar-pos",
            )

            yield Label("Sidebar width (columns)")
            yield Input(str(cfg.sidebar_width), id="set-sidebar-width", placeholder="20–80")

            # ── Data / timing ───────────────────────────────────────────
            yield Static("Data", classes="set-section-hdr")

            yield Label("Days ahead")
            yield Input(str(cfg.days_ahead), id="set-days-ahead", placeholder="1–365")

            yield Label("Past hours shown")
            yield Input(str(cfg.past_hours), id="set-past-hours", placeholder="0–8760")

            yield Label("Auto-refresh interval (seconds)")
            yield Input(str(cfg.auto_refresh_sec), id="set-auto-refresh", placeholder="30–3600")

            # ── Extra keybindings ───────────────────────────────────────
            yield Static("Extra keybindings", classes="set-section-hdr")
            yield Static(
                "Add an alternate key for any action.  Leave blank to keep the built-in default.",
                classes="set-help",
            )

            for action in REBINDABLE_ACTIONS:
                yield Label(action.replace("_", " "))
                yield Input(
                    cfg.keybindings.get(action, ""),
                    id=f"set-kb-{action}",
                    placeholder="e.g. ctrl+r  or  f5",
                )

            yield Static("", id="set-conflict-msg")

        with Horizontal(id="set-buttons"):
            yield Button("Save & Apply", id="set-save", variant="primary")
            yield Button("Cancel", id="set-cancel")

        yield Footer()

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _read_form(self) -> dict[str, Any] | None:
        """Collect all form values.  Returns None if any numeric field is invalid."""
        cfg = self._owner.cfg
        try:
            theme_sel = self.query_one("#set-theme", Select)
            sidebar_sel = self.query_one("#set-sidebar-pos", Select)
            sidebar_w_inp = self.query_one("#set-sidebar-width", Input)
            days_inp = self.query_one("#set-days-ahead", Input)
            past_inp = self.query_one("#set-past-hours", Input)
            auto_inp = self.query_one("#set-auto-refresh", Input)

            theme = str(theme_sel.value) if theme_sel.value is not Select.BLANK else cfg.theme
            sidebar_pos = str(sidebar_sel.value) if sidebar_sel.value is not Select.BLANK else cfg.sidebar_position
            sidebar_w = int(sidebar_w_inp.value or cfg.sidebar_width)
            days_ahead = int(days_inp.value or cfg.days_ahead)
            past_hours = int(past_inp.value or cfg.past_hours)
            auto_refresh = int(auto_inp.value or cfg.auto_refresh_sec)
        except ValueError:
            return None

        keybindings: dict[str, str] = {}
        for action in REBINDABLE_ACTIONS:
            inp = self.query_one(f"#set-kb-{action}", Input)
            val = inp.value.strip()
            if val:
                keybindings[action] = val

        return {
            "theme": theme,
            "sidebar_position": sidebar_pos,
            "sidebar_width": sidebar_w,
            "days_ahead": days_ahead,
            "past_hours": past_hours,
            "auto_refresh_sec": auto_refresh,
            "keybindings": keybindings,
        }

    def _show_error(self, msg: str) -> None:
        self.query_one("#set-conflict-msg", Static).update(f"[red]{msg}[/red]")

    # ── Event handlers ──────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "set-cancel":
            self.dismiss(None)
        elif event.button.id == "set-save":
            self.action_save()

    def action_save(self) -> None:
        result = self._read_form()
        if result is None:
            self._show_error("Invalid values — all numeric fields must be whole numbers.")
            return
        conflict = _find_conflicts(result["keybindings"])
        if conflict:
            self._show_error(f"Keybinding conflict: {conflict}")
            return
        self.dismiss(result)

    def action_close(self) -> None:
        self.dismiss(None)
