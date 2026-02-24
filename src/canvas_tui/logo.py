"""Canvas LMS logo — rendered from the official Canvas circular icon.

The Canvas logo is a circular starburst/pinwheel pattern. This is a
half-block character rendering of the actual Canvas LMS logo PNG,
matching the approach from GideonWolfe/canvas-tui.
"""

from __future__ import annotations

# Canvas circular icon — half-block rendered from official PNG
# ~30 cols wide, 12 rows tall, rendered in Canvas brand red
CANVAS_ICON = (
    "[bold red]"
    "           ▄▄▄▄▄▄▄           \n"
    "        ▄▄█  ▀████▀ ▄█▄▄    \n"
    "      ▄████    ▄▄▄   ▀████▄  \n"
    "      ▀▀▀▀▄█▄  ▀▀▀  ▄▄ ▀▀▀▀ \n"
    "    ▄▄▄    ▀        ▀▀    ▄▄▄\n"
    "    ████ ▄▄           ▄▄ ████\n"
    "    ███▀ ▀▀           ▀▀ ▀███\n"
    "    ▀▀    ▄▄▄       ▄▄     ▀▀\n"
    "      ████▄▀▀  ▄█▄  ▀▀▄████  \n"
    "       ▀███    ▄█▄   ████▀   \n"
    "         ▀▀  ███████  ▀▀     \n"
    "               ▀▀            "
    "[/bold red]"
)

# Icon + CANVAS text side by side (for wide displays, ~62 cols)
CANVAS_LOGO_WIDE = (
    "[bold red]"
    "       ▄▄▄▄▄▄▄        [/bold red]                          \n"
    "[bold red]    ▄▄█  ▀████▀ ▄█▄▄   [/bold red][bold red] ██████  █████  ██   ██[/bold red]\n"
    "[bold red]  ▄████    ▄▄▄   ▀████▄ [/bold red][bold red]██      ██   ██ ███  ██[/bold red]\n"
    "[bold red]  ▀▀▀▀▄█▄  ▀▀▀  ▄▄ ▀▀▀▀[/bold red][bold red]██      ███████ ██ █ ██[/bold red]\n"
    "[bold red]▄▄▄    ▀        ▀▀    ▄▄▄[/bold red][bold red]██   ██ ██  ███[/bold red]\n"
    "[bold red]████ ▄▄           ▄▄ ████[/bold red][bold red] ██████ ██   ██[/bold red]\n"
    "[bold red]███▀ ▀▀           ▀▀ ▀███[/bold red]                          \n"
    "[bold red]▀▀    ▄▄▄       ▄▄     ▀▀[/bold red][bold red]██   ██  █████  ███████[/bold red]\n"
    "[bold red]  ████▄▀▀  ▄█▄  ▀▀▄████  [/bold red][bold red] ██ ██  ██   ██ ██     [/bold red]\n"
    "[bold red]   ▀███    ▄█▄   ████▀   [/bold red][bold red]  ███   ███████ ███████[/bold red]\n"
    "[bold red]     ▀▀  ███████  ▀▀     [/bold red][bold red]  ███   ██   ██      ██[/bold red]\n"
    "[bold red]           ▀▀            [/bold red][bold red]   █    ██   ██ ███████[/bold red]"
)

# Compact — just the text (for narrow panels)
CANVAS_LOGO_SMALL = "[bold red]CANVAS[/bold red] [dim]LMS[/dim]"


def get_logo(width: int = 80) -> str:
    """Select best logo for available width."""
    if width >= 60:
        return CANVAS_LOGO_WIDE
    if width >= 32:
        return CANVAS_ICON
    return CANVAS_LOGO_SMALL
