"""Tests for Canvas ASCII logo module."""

from canvas_tui.logo import (
    CANVAS_LOGO_FULL,
    CANVAS_LOGO_MED,
    CANVAS_LOGO_SMALL,
    get_logo,
)


class TestLogo:
    def test_full_has_block_chars(self):
        assert "██" in CANVAS_LOGO_FULL

    def test_full_is_red(self):
        assert "red" in CANVAS_LOGO_FULL

    def test_med_has_box_drawing(self):
        assert "┌" in CANVAS_LOGO_MED

    def test_small_has_canvas(self):
        assert "CANVAS" in CANVAS_LOGO_SMALL

    def test_get_logo_wide(self):
        logo = get_logo(80)
        assert "██" in logo

    def test_get_logo_medium(self):
        logo = get_logo(40)
        assert "┌" in logo

    def test_get_logo_narrow(self):
        logo = get_logo(10)
        assert "CANVAS" in logo
