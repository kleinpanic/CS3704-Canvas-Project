"""Tests for theme system."""

from __future__ import annotations

from canvas_tui.theme import DARK_THEME, LIGHT_THEME, get_theme


class TestTheme:
    def test_dark_theme_has_all_fields(self):
        t = DARK_THEME
        assert t.name == "dark"
        assert t.bg
        assert t.text
        assert t.primary
        assert t.success
        assert t.error
        assert t.canvas_logo
        assert t.overdue
        assert t.urgent
        assert t.soon
        assert t.today
        assert t.upcoming
        assert t.normal

    def test_light_theme_has_all_fields(self):
        t = LIGHT_THEME
        assert t.name == "light"
        assert t.bg
        assert t.text

    def test_themes_differ(self):
        assert DARK_THEME.bg != LIGHT_THEME.bg
        assert DARK_THEME.text != LIGHT_THEME.text

    def test_get_theme_default(self):
        assert get_theme().name == "dark"

    def test_get_theme_light(self):
        assert get_theme("light").name == "light"

    def test_get_theme_unknown_falls_back(self):
        assert get_theme("neon").name == "dark"

    def test_frozen(self):
        """Theme dataclass should be immutable."""
        try:
            DARK_THEME.name = "changed"  # type: ignore
            assert False, "Should have raised"
        except AttributeError:
            pass  # Expected — frozen=True
