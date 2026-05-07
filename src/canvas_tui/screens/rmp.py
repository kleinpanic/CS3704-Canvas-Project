# SPDX-License-Identifier: GPL-3.0-or-later
"""RMP TUI screen — search → results → details professor ratings view."""

from __future__ import annotations

import contextlib

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Input, Static

from ..keybindings import REGISTRY
from ..rmp.client import RMPClient
from ..rmp.models import ProfessorRating


class RMPScreen(Screen):
    """Three-state Rate My Professors search screen.

    States: "search" → "results" → "details"
    Press q/Escape to go back at any stage.
    """

    screen_name = "rmp"

    DEFAULT_CSS = """
    RMPScreen {
        layout: vertical;
    }
    #rmp-header {
        height: auto;
        padding: 0 1;
        border-bottom: solid #30363d;
    }
    #rmp-search-input {
        height: 3;
        margin: 0 1;
    }
    #rmp-results-table {
        height: 1fr;
    }
    #rmp-details-panel {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    #rmp-footer {
        height: 1;
        padding: 0 1;
        background: #161b22;
        color: #8b949e;
    }
    """

    BINDINGS = [
        ("q", "pop_screen", "Back"),
        ("escape", "pop_screen", "Back"),
        ("enter", "select", "Search/Select"),
    ]

    def __init__(self, rmp_client: RMPClient | None = None) -> None:
        super().__init__()
        self._state = "search"
        self._professors: list[ProfessorRating] = []
        self._rmp_client = rmp_client

        for key, action, desc in self.BINDINGS:
            with contextlib.suppress(ValueError):
                REGISTRY.register(self.screen_name, key, action, desc)

    def _get_client(self) -> RMPClient | None:
        if self._rmp_client is not None:
            return self._rmp_client
        try:
            from ..config import load_config

            cfg = load_config()
            return RMPClient.from_canvas_url(cfg.base_url)
        except Exception:
            return None

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Rate My Professors[/bold]  [dim]Search for a professor[/dim]",
            id="rmp-header",
        )
        yield Input(placeholder="Enter professor name…", id="rmp-search-input")
        yield DataTable(id="rmp-results-table")
        yield Static("", id="rmp-details-panel")
        yield Static("[dim]Enter=search/select  q=back  Esc=back[/dim]", id="rmp-footer")

    def on_mount(self) -> None:
        table = self.query_one("#rmp-results-table", DataTable)
        table.add_columns("Name", "Rating", "Difficulty", "Would Take Again", "# Ratings")
        table.display = False
        self.query_one("#rmp-details-panel", Static).display = False
        self.query_one("#rmp-search-input", Input).focus()

    def action_select(self) -> None:
        if self._state == "search":
            inp = self.query_one("#rmp-search-input", Input)
            query = inp.value.strip()
            if query:
                self._do_search(query)
        elif self._state == "results":
            table = self.query_one("#rmp-results-table", DataTable)
            row_idx = table.cursor_row
            if row_idx is not None and row_idx < len(self._professors):
                self._show_details(self._professors[row_idx])

    def _do_search(self, query: str) -> None:
        client = self._get_client()
        if client is None:
            self.query_one("#rmp-details-panel", Static).update(
                "[red]RMP client unavailable — check Canvas base URL config[/red]"
            )
            self.query_one("#rmp-details-panel", Static).display = True
            return

        try:
            results = client.search_professor(query)
        except Exception as exc:
            self.query_one("#rmp-details-panel", Static).update(f"[red]Search failed:[/red] {exc}")
            self.query_one("#rmp-details-panel", Static).display = True
            return

        self._professors = results
        table = self.query_one("#rmp-results-table", DataTable)
        table.clear()

        if not results:
            self.query_one("#rmp-details-panel", Static).update("[dim]No results found. Try a different name.[/dim]")
            self.query_one("#rmp-details-panel", Static).display = True
            self.query_one("#rmp-search-input", Input).display = True
            table.display = False
            return

        for prof in results:
            table.add_row(
                prof.full_name,
                prof.display_rating,
                prof.display_difficulty,
                prof.display_would_take_again,
                str(prof.num_ratings),
            )

        self.query_one("#rmp-search-input", Input).display = False
        self.query_one("#rmp-details-panel", Static).display = False
        table.display = True
        table.focus()
        self._state = "results"

    def _show_details(self, prof: ProfessorRating) -> None:
        dept = prof.department or "Unknown"
        inst = prof.institution or "Unknown"
        tags_str = ", ".join(prof.tags[:5]) if prof.tags else "—"
        detail_text = (
            f"[bold]{prof.full_name}[/bold]\n"
            f"Department: {dept}\n"
            f"Institution: {inst}\n\n"
            f"Rating:         {prof.display_rating}\n"
            f"Difficulty:     {prof.display_difficulty}\n"
            f"Would Take Again: {prof.display_would_take_again}\n"
            f"# Ratings:      {prof.num_ratings}\n\n"
            f"[dim]Tags: {tags_str}[/dim]\n\n"
            f"[dim]Press q or Esc to return[/dim]"
        )
        panel = self.query_one("#rmp-details-panel", Static)
        panel.update(detail_text)
        panel.display = True
        self.query_one("#rmp-results-table", DataTable).display = False
        self._state = "details"
