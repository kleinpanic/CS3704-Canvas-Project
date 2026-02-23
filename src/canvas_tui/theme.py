"""Theme system for Canvas TUI — dark/light toggle with named color tokens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeColors:
    """Named color tokens for a theme."""

    name: str
    # Base
    bg: str
    surface: str
    panel: str
    border: str
    # Text
    text: str
    text_muted: str
    text_accent: str
    # Semantic
    primary: str
    secondary: str
    success: str
    warning: str
    error: str
    info: str
    # Canvas brand
    canvas_logo: str
    # Due date urgency
    overdue: str
    urgent: str      # < 8h
    soon: str         # < 12h
    today: str        # < 24h
    upcoming: str     # < 48h
    normal: str       # > 48h


DARK_THEME = ThemeColors(
    name="dark",
    bg="#0d1117",
    surface="#161b22",
    panel="#21262d",
    border="#30363d",
    text="#c9d1d9",
    text_muted="#8b949e",
    text_accent="#58a6ff",
    primary="#58a6ff",
    secondary="#bc8cff",
    success="#3fb950",
    warning="#d29922",
    error="#f85149",
    info="#58a6ff",
    canvas_logo="cyan",
    overdue="#f85149",
    urgent="#ff7b72",
    soon="#d29922",
    today="#3fb950",
    upcoming="#58a6ff",
    normal="#c9d1d9",
)

LIGHT_THEME = ThemeColors(
    name="light",
    bg="#ffffff",
    surface="#f6f8fa",
    panel="#eaeef2",
    border="#d0d7de",
    text="#1f2328",
    text_muted="#656d76",
    text_accent="#0969da",
    primary="#0969da",
    secondary="#8250df",
    success="#1a7f37",
    warning="#9a6700",
    error="#cf222e",
    info="#0969da",
    canvas_logo="dark_cyan",
    overdue="#cf222e",
    urgent="#cf222e",
    soon="#9a6700",
    today="#1a7f37",
    upcoming="#0969da",
    normal="#1f2328",
)


def get_theme(name: str = "dark") -> ThemeColors:
    """Get theme by name."""
    if name == "light":
        return LIGHT_THEME
    return DARK_THEME
