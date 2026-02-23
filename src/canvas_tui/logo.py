"""Canvas LMS logo — block-character wordmark in Canvas brand red.

Clean, readable block letters similar to GideonWolfe/canvas-tui's
cyan CANVAS wordmark, but in Canvas brand red.
"""

from __future__ import annotations

# Full block-letter CANVAS wordmark (48 cols wide, 5 lines tall)
CANVAS_LOGO_FULL = (
    "[bold red]"
    " ██████  █████  ██   ██ ██   ██  █████  ███████\n"
    "██      ██   ██ ███  ██ ██   ██ ██   ██ ██     \n"
    "██      ███████ ██ █ ██ ██   ██ ███████ ███████\n"
    "██      ██   ██ ██  ███  ██ ██  ██   ██      ██\n"
    " ██████ ██   ██ ██   ██   ███   ██   ██ ███████"
    "[/bold red]"
)

# Medium — box-drawing CANVAS (21 cols, 3 lines)
CANVAS_LOGO_MED = (
    "[bold red]"
    "┌─┐┌─┐┌┐┌┬  ┬┌─┐┌─┐\n"
    "│  ├─┤│││└┐┌┘├─┤└─┐\n"
    "└─┘┴ ┴┘└┘ └┘ ┴ ┴└─┘"
    "[/bold red]"
)

# Compact one-liner
CANVAS_LOGO_SMALL = "[bold red]CANVAS[/bold red] [dim]LMS[/dim]"


def get_logo(width: int = 80) -> str:
    """Select best logo for available width."""
    if width >= 50:
        return CANVAS_LOGO_FULL
    if width >= 22:
        return CANVAS_LOGO_MED
    return CANVAS_LOGO_SMALL
