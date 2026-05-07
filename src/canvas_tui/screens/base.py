# SPDX-License-Identifier: GPL-3.0-or-later
"""Abstract base screen for all canvas-tui screens."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from ..keybindings import REGISTRY


class BaseScreen(Screen):
    """Abstract base screen providing keybinding help overlay support.

    Concrete screens set the class attribute `screen_name` so the Registry
    knows which binding set to display.
    """

    screen_name: str = ""

    def show_help_overlay(self) -> None:
        help_text = REGISTRY.get_help(self.screen_name)
        if not help_text:
            help_text = "(no keybindings registered for this screen)"
        self.app.push_screen(_HelpOverlay(help_text))


class _HelpOverlay(Screen):
    """Minimal modal that shows a help text and closes on any key."""

    DEFAULT_CSS = """
    _HelpOverlay {
        align: center middle;
    }
    #overlay-panel {
        border: solid #30363d;
        padding: 1 2;
        width: auto;
        min-width: 40;
        max-width: 80;
        height: auto;
    }
    """

    BINDINGS = [("escape", "pop_screen", "Close"), ("question_mark", "pop_screen", "Close")]

    def __init__(self, help_text: str) -> None:
        super().__init__()
        self._help_text = help_text

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]Keybindings[/bold]\n\n{self._help_text}\n\n[dim]Press Esc to close[/dim]",
            id="overlay-panel",
        )

    def on_key(self, event: object) -> None:
        self.app.pop_screen()
