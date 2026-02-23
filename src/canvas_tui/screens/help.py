"""Help screen with categorized keybindings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Static

HELP_TEXT = """\
[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]
[bold cyan]        Canvas TUI — Keyboard Reference       [/bold cyan]
[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]

[bold]Navigation[/bold]
  [cyan]↑ ↓[/cyan]       Move through items
  [cyan]Enter[/cyan]     Open full details view
  [cyan]d[/cyan]         Quick preview in sidebar
  [cyan]Bksp/Esc[/cyan]  Go back from any screen

[bold]Actions[/bold]
  [cyan]o[/cyan]         Open item in browser
  [cyan]g[/cyan]         Open course page in browser
  [cyan]y[/cyan]         Copy URL to clipboard
  [cyan]w[/cyan]         Download attachments
  [cyan]c[/cyan]         Export all items to ICS
  [cyan]C[/cyan]         Export ICS + import to calcurse

[bold]Filtering & Visibility[/bold]
  [cyan]/[/cyan]         Toggle search filter
  [cyan]x[/cyan]         Cycle: visible → dim → hidden
  [cyan]H[/cyan]         Show/hide hidden items

  [dim]Filter syntax: course:CS3214 type:assignment status:graded[/dim]
  [dim]Short prefixes: c: t: s: has:points has:due[/dim]

[bold]Views[/bold]
  [cyan]S[/cyan]         Syllabi browser
  [cyan]A[/cyan]         Announcements
  [cyan]G[/cyan]         Grades overview
  [cyan]F[/cyan]         File manager
  [cyan]W[/cyan]         Calendar week view
  [cyan]?[/cyan]         This help screen

[bold]Pomodoro Timer[/bold]
  [cyan]1[/cyan]         Start 30 min
  [cyan]2[/cyan]         Start 60 min
  [cyan]3[/cyan]         Start 120 min
  [cyan]P[/cyan]         Custom duration
  [cyan]0[/cyan]         Stop timer

[bold]General[/bold]
  [cyan]r[/cyan]         Refresh data from Canvas
  [cyan]s[/cyan]         Cycle sort: due → course → type → title
  [cyan]T[/cyan]         Toggle dark/light theme
  [cyan]q[/cyan]         Quit

[dim]Press Esc or ? to close this screen[/dim]
"""


class HelpScreen(Screen):
    """Full-screen help overlay."""

    BINDINGS = [
        ("escape", "dismiss_help", "Close"),
        ("question_mark", "dismiss_help", "Close"),
        ("q", "dismiss_help", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-scroll"):
            yield Static(HELP_TEXT, id="help-text")
        yield Footer()

    def on_key(self, event: Key) -> None:
        if event.key in ("escape", "question_mark", "q"):
            event.stop()
            self.app.pop_screen()

    def action_dismiss_help(self) -> None:
        self.app.pop_screen()
