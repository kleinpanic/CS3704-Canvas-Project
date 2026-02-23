"""Tests for utility functions."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from canvas_tui.utils import (
    absolute_url,
    legacy_item_key,
    rel_time,
    sanitize_filename,
    stable_item_key,
    strip_html,
)


class TestStripHtml:
    def test_simple_tags(self):
        assert strip_html("<p>Hello</p>") == "Hello"

    def test_nested_tags(self):
        assert "Hello" in strip_html("<div><p><b>Hello</b></p></div>")

    def test_script_tags_stripped(self):
        result = strip_html("<p>Safe</p><script>alert('xss')</script><p>Also safe</p>")
        assert "alert" not in result
        assert "Safe" in result
        assert "Also safe" in result

    def test_entities(self):
        result = strip_html("&amp; &lt; &gt;")
        assert "&" in result
        assert "<" in result

    def test_empty(self):
        assert strip_html("") == ""
        assert strip_html(None) == ""

    def test_attributes_with_gt(self):
        # The old regex-based stripper would fail on this
        result = strip_html('<a href="test>link">Click</a>')
        assert "Click" in result

    def test_br_adds_newline(self):
        result = strip_html("line1<br>line2")
        assert "\n" in result


class TestRelTime:
    def test_future(self):
        tz = "America/New_York"
        future = dt.datetime.now(ZoneInfo(tz)) + dt.timedelta(hours=2, minutes=30)
        result = rel_time(future, tz)
        assert "in" in result
        assert "h" in result

    def test_past(self):
        tz = "America/New_York"
        past = dt.datetime.now(ZoneInfo(tz)) - dt.timedelta(hours=5)
        result = rel_time(past, tz)
        assert "ago" in result

    def test_far_future(self):
        tz = "America/New_York"
        far = dt.datetime.now(ZoneInfo(tz)) + dt.timedelta(days=3)
        result = rel_time(far, tz)
        assert "d" in result


class TestSanitizeFilename:
    def test_removes_special_chars(self):
        assert "/" not in sanitize_filename("a/b\\c:d")
        assert "\\" not in sanitize_filename("a\\b")

    def test_strips_whitespace(self):
        result = sanitize_filename("  hello  world  ")
        assert result == "hello world"

    def test_empty_returns_untitled(self):
        assert sanitize_filename("") == "untitled"


class TestAbsoluteUrl:
    def test_already_absolute(self):
        assert absolute_url("https://example.com/page", "https://base.com") == "https://example.com/page"

    def test_relative_url(self):
        result = absolute_url("/courses/123", "https://canvas.vt.edu")
        assert result.startswith("https://canvas.vt.edu")
        assert "/courses/123" in result


class TestStableItemKey:
    def test_basic(self):
        key = stable_item_key(123, 456, "assignment")
        assert key == "123:456:assignment"

    def test_none_values(self):
        key = stable_item_key(None, None, "quiz")
        assert key == "::quiz"

    def test_deterministic(self):
        k1 = stable_item_key(1, 2, "assignment")
        k2 = stable_item_key(1, 2, "assignment")
        assert k1 == k2


class TestLegacyItemKey:
    def test_includes_hash(self):
        key = legacy_item_key(123, 456, "assignment", "HW3")
        assert "123" in key
        assert "456" in key
