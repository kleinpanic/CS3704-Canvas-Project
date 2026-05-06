"""Tests for canvas_tui.pii — PII scrub module."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from canvas_tui.pii import SCRUB_KEYS, scrub_doc, scrub_string


class TestScrubStringRegex:
    def test_email_scrubbed(self):
        result = scrub_string("john.doe@example.com", hf_token="")
        assert "john.doe@example.com" not in result
        assert "[EMAIL]" in result

    def test_phone_scrubbed(self):
        result = scrub_string("555-123-4567", hf_token="")
        assert "555-123-4567" not in result
        assert "[PHONE]" in result

    def test_ssn_scrubbed(self):
        result = scrub_string("123-45-6789", hf_token="")
        assert "123-45-6789" not in result
        assert "[SSN]" in result

    def test_empty_string_unchanged(self):
        assert scrub_string("", hf_token="") == ""

    def test_non_string_passthrough(self):
        assert scrub_string(42, hf_token="") == 42

    def test_non_ascii_no_crash(self):
        result = scrub_string("François Étienne", hf_token="")
        assert isinstance(result, str)

    def test_clean_text_unchanged(self):
        text = "Assignment 1 due next week"
        assert scrub_string(text, hf_token="") == text


class TestScrubDoc:
    def test_scrub_keys_name_field(self):
        doc = {"name": "Alice Smith alice@example.com", "id": 99}
        result = scrub_doc(doc, hf_token="")
        assert "alice@example.com" not in result["name"]
        assert "[EMAIL]" in result["name"]
        assert result["id"] == 99

    def test_course_name_in_scrub_keys(self):
        doc = {"course_name": "Data Structures user@vt.edu", "points": 100}
        result = scrub_doc(doc, hf_token="")
        assert "user@vt.edu" not in result["course_name"]
        assert result["points"] == 100

    def test_nested_list_handled(self):
        doc = [{"name": "bob@x.com"}]
        result = scrub_doc(doc, hf_token="")
        assert "bob@x.com" not in result[0]["name"]
        assert "[EMAIL]" in result[0]["name"]

    def test_non_scrub_key_preserved(self):
        doc = {"type": "course_snapshot", "points": 42}
        result = scrub_doc(doc, hf_token="")
        assert result["type"] == "course_snapshot"
        assert result["points"] == 42

    def test_string_value_outside_keys_scrubbed(self):
        doc = {"unknown_key": "call 555-999-8888 now"}
        result = scrub_doc(doc, hf_token="")
        assert "555-999-8888" not in result["unknown_key"]

    def test_empty_dict(self):
        assert scrub_doc({}, hf_token="") == {}

    def test_non_string_values_preserved(self):
        doc = {"points": 100, "submitted": True, "score": 3.14}
        result = scrub_doc(doc, hf_token="")
        assert result == doc


class TestScrubKeys:
    def test_course_name_in_scrub_keys(self):
        assert "course_name" in SCRUB_KEYS

    def test_name_in_scrub_keys(self):
        assert "name" in SCRUB_KEYS

    def test_title_in_scrub_keys(self):
        assert "title" in SCRUB_KEYS


class TestPiiranha:
    def test_piiranha_called_when_token_provided(self):
        with patch("canvas_tui.pii._piiranha_call", return_value="[NAME] lives here") as mock_p:
            result = scrub_string("A long enough string to trigger piiranha path here", hf_token="fake_token")
        mock_p.assert_called_once()
        assert result == "[NAME] lives here"

    def test_piiranha_fallback_to_regex_on_none(self):
        with patch("canvas_tui.pii._piiranha_call", return_value=None):
            result = scrub_string("call 555-123-4567 for info", hf_token="fake_token")
        assert "555-123-4567" not in result
        assert "[PHONE]" in result

    def test_no_piiranha_without_token(self):
        with patch("canvas_tui.pii._piiranha_call") as mock_p:
            scrub_string("john@example.com", hf_token="")
        mock_p.assert_not_called()

    def test_short_string_skips_piiranha(self):
        with patch("canvas_tui.pii._piiranha_call") as mock_p:
            scrub_string("hi@x.com", hf_token="mytoken")
        mock_p.assert_not_called()

    def test_token_not_in_piiranha_error(self):
        import canvas_tui.pii as pii_mod
        original = pii_mod._piiranha_available
        pii_mod._piiranha_available = True
        try:
            import urllib.error
            with patch("canvas_tui.pii.urllib.request.urlopen",
                       side_effect=urllib.error.HTTPError(
                           url="", code=401, msg="Unauthorized",
                           hdrs=None, fp=None)):
                result = pii_mod._piiranha_call("some text here", "secret_token_abc")
            assert result is None
            assert "secret_token_abc" not in str(result)
        finally:
            pii_mod._piiranha_available = original
