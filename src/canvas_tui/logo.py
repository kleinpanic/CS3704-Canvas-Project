"""Canvas ASCII logo and branding elements.

Inspired by GideonWolfe/canvas-tui's logo approach, but rendered as
Rich-markup ASCII art instead of base64 PNG blobs.
"""

from __future__ import annotations

# Full Canvas wordmark — block unicode, brand cyan + red accent
CANVAS_WORDMARK = (
    "[bold cyan]"
    "  ██████╗ █████╗ ███╗   ██╗██╗   ██╗ █████╗ ███████╗\n"
    " ██╔════╝██╔══██╗████╗  ██║██║   ██║██╔══██╗██╔════╝\n"
    " ██║     ███████║██╔██╗ ██║██║   ██║███████║███████╗\n"
    " ██║     ██╔══██║██║╚██╗██║╚██╗ ██╔╝██╔══██║╚════██║\n"
    " ╚██████╗██║  ██║██║ ╚████║ ╚████╔╝ ██║  ██║███████║\n"
    " ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝  ╚═══╝  ╚═╝  ╚═╝╚══════╝"
    "[/bold cyan]"
)

# Compact logo — for small terminals or sidebar
CANVAS_COMPACT = (
    "[bold cyan]╔═╗┌─┐┌┐┌┬  ┬┌─┐┌─┐[/bold cyan]\n"
    "[bold cyan]║  ├─┤│││└┐┌┘├─┤└─┐[/bold cyan]\n"
    "[bold cyan]╚═╝┴ ┴┘└┘ └┘ ┴ ┴└─┘[/bold cyan]"
)

# Canvas "C" shield — icon-style for dashboard headers
CANVAS_SHIELD = (
    "[bold red]   ╔══════════╗[/bold red]\n"
    "[bold red]   ║[/bold red][bold white]  ██████  [/bold white][bold red]║[/bold red]\n"
    "[bold red]   ║[/bold red][bold white] ██[/bold white]       [bold red]║[/bold red]\n"
    "[bold red]   ║[/bold red][bold white] ██[/bold white]       [bold red]║[/bold red]\n"
    "[bold red]   ║[/bold red][bold white] ██[/bold white]       [bold red]║[/bold red]\n"
    "[bold red]   ║[/bold red][bold white]  ██████  [/bold white][bold red]║[/bold red]\n"
    "[bold red]   ╚══════════╝[/bold red]"
)

# One-liner brand
CANVAS_INLINE = "[bold cyan]Canvas[/bold cyan] [dim]LMS Terminal[/dim]"


def get_logo(width: int = 80) -> str:
    """Pick the best logo variant for the available width."""
    if width >= 58:
        return CANVAS_WORDMARK
    if width >= 24:
        return CANVAS_COMPACT
    return CANVAS_INLINE
