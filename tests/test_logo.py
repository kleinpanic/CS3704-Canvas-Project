"""Tests for Canvas ASCII logo module."""

from canvas_tui.logo import (
    CANVAS_COMPACT,
    CANVAS_INLINE,
    CANVAS_SHIELD,
    CANVAS_WORDMARK,
    get_logo,
)


class TestLogo:
    def test_wordmark_contains_canvas(self):
        # The block chars spell CANVAS
        assert "██" in CANVAS_WORDMARK
        assert "[cyan]" in CANVAS_WORDMARK or "[bold cyan]" in CANVAS_WORDMARK

    def test_compact_exists(self):
        assert len(CANVAS_COMPACT) > 10
        assert "┌" in CANVAS_COMPACT or "╔" in CANVAS_COMPACT

    def test_shield_exists(self):
        assert "║" in CANVAS_SHIELD

    def test_inline_exists(self):
        assert "Canvas" in CANVAS_INLINE

    def test_get_logo_wide(self):
        logo = get_logo(80)
        assert "██" in logo  # Should return wordmark

    def test_get_logo_narrow(self):
        logo = get_logo(30)
        assert "┌" in logo or "╔" in logo  # Should return compact

    def test_get_logo_tiny(self):
        logo = get_logo(10)
        assert "Canvas" in logo  # Should return inline
