"""Tests for Canvas logo module."""

from canvas_tui.logo import (
    CANVAS_ICON,
    CANVAS_LOGO_SMALL,
    CANVAS_LOGO_WIDE,
    get_logo,
)


class TestLogo:
    def test_icon_has_half_blocks(self):
        assert "▄" in CANVAS_ICON or "█" in CANVAS_ICON

    def test_icon_is_red(self):
        assert "red" in CANVAS_ICON

    def test_wide_has_icon_and_text(self):
        assert "▄" in CANVAS_LOGO_WIDE
        assert "██" in CANVAS_LOGO_WIDE

    def test_small_has_text(self):
        assert "CANVAS" in CANVAS_LOGO_SMALL

    def test_get_logo_wide(self):
        logo = get_logo(80)
        assert "▄" in logo

    def test_get_logo_medium(self):
        logo = get_logo(35)
        assert "▄" in logo

    def test_get_logo_narrow(self):
        logo = get_logo(10)
        assert "CANVAS" in logo
