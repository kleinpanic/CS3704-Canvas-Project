# SPDX-License-Identifier: GPL-3.0-or-later
"""Main Canvas TUI application — screen router."""

from __future__ import annotations

import shutil
import sys

from textual.app import App, ComposeResult

from .keybindings import REGISTRY
from .screens.home import HomeScreen
from .theme import set_theme


class CanvasTUI(App):
    """Thin Textual App that routes to HomeScreen on mount.

    All state (api, cfg, items, etc.) lives in HomeScreen. The App is
    intentionally minimal — it validates keybindings at startup and pushes
    the home screen.
    """

    from . import __version__

    title = f"CanvasTUI v{__version__}"

    def __init__(self, **overrides: object) -> None:
        """Create the app.

        overrides: CLI-specified overrides forwarded to HomeScreen.
            Supported keys: no_cache, days_ahead, past_hours, theme.
        """
        super().__init__()
        self._cli_overrides: dict[str, object] = overrides

        try:
            REGISTRY.validate_all()
        except ValueError as exc:
            print(f"Keybinding conflict detected:\n{exc}", file=sys.stderr)
            sys.exit(1)

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        home = HomeScreen()

        overrides = self._cli_overrides
        if overrides.get("no_cache"):
            home.api._no_cache = True
        days_ahead = overrides.get("days_ahead")
        if days_ahead is not None:
            home.cfg.days_ahead = days_ahead
        past_hours = overrides.get("past_hours")
        if past_hours is not None:
            home.cfg.past_hours = past_hours
        theme = overrides.get("theme")
        if theme == "light":
            home._theme = set_theme("light")
            self.dark = False
            home.cfg.theme = "light"
        elif theme == "dark":
            home._theme = set_theme("dark")
            self.dark = True
            home.cfg.theme = "dark"

        self.push_screen(home)


def _console_size() -> tuple[int, int] | None:
    try:
        ts = shutil.get_terminal_size(fallback=(0, 0))
        if ts.columns > 0 and ts.lines > 0:
            return ts.columns, ts.lines
    except Exception:
        pass
    return None


def main() -> None:
    """Entry point for the Canvas TUI application."""
    from .cli import handle_non_tui_commands, parse_args

    args = parse_args()

    if handle_non_tui_commands(args):
        return

    if getattr(args, "ascii", False):
        import os as _os

        _os.environ["CANVAS_ASCII"] = "1"
        from . import compat as _compat

        _compat.USE_ASCII = True
        _compat.BLOCK_FULL = "#"
        _compat.BLOCK_EMPTY = "-"
        _compat.BLOCK_HALF = "+"
        _compat.HEAT_CHARS = " .:-=#"
        _compat.SPARKLINE_CHARS = ".,:-=+|#"

    app = CanvasTUI(
        no_cache=args.no_cache,
        days_ahead=args.days_ahead,
        past_hours=args.past_hours,
        theme=getattr(args, "theme", None),
    )
    app.run(size=_console_size())
