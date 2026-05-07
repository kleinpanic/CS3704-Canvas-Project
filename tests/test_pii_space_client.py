# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for canvas_tui.pii.scrub_via_space() — Space HTTP client.

All tests mock canvas_tui.pii.urllib.request.urlopen (NOT requests).
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from canvas_tui.pii import scrub_doc, scrub_via_space, CANVAS_PII_SPACE_URL


def _make_response(body: dict, status: int = 200) -> MagicMock:
    """Build a mock urllib response context manager."""
    raw = json.dumps(body).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = {}
    if retry_after:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="http://mock/scrub",
        code=code,
        msg=f"HTTP {code}",
        hdrs=hdrs,
        fp=None,
    )


class TestScrubHappyPath:
    """Test 1: /scrub happy path — successful 200 response."""

    def test_scrub_happy_path(self):
        doc = {"text": "Hello world"}
        scrubbed = {"text": "@PERSON_1"}
        response_body = {
            "document": scrubbed,
            "redactions": [{"token": "@PERSON_1", "count": 1}],
            "registry": {"Alice": "@PERSON_1"},
        }
        mock_resp = _make_response(response_body)

        with patch("canvas_tui.pii.urllib.request.urlopen", return_value=mock_resp):
            result = scrub_via_space(doc, "https://example.hf.space")

        assert result == scrubbed

    def test_scrub_sends_correct_payload(self):
        doc = {"text": "test"}
        response_body = {"document": doc, "redactions": [], "registry": {}}
        mock_resp = _make_response(response_body)

        with patch("canvas_tui.pii.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            scrub_via_space(doc, "https://example.hf.space")

        call_args = mock_open.call_args
        request_obj = call_args[0][0]
        assert request_obj.full_url == "https://example.hf.space/scrub"
        payload = json.loads(request_obj.data)
        assert payload == {"document": doc}

    def test_scrub_sets_canvas_tracker_user_agent(self):
        doc = {"text": "test"}
        response_body = {"document": doc, "redactions": [], "registry": {}}
        mock_resp = _make_response(response_body)

        with patch("canvas_tui.pii.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            scrub_via_space(doc, "https://example.hf.space")

        request_obj = mock_open.call_args[0][0]
        ua = request_obj.get_header("User-agent")
        assert ua is not None
        assert "canvas-tracker" in ua.lower()


class TestColdStartRetry503:
    """Test 3: 503 retry logic — first call 503, second call succeeds."""

    def test_retry_on_503_succeeds(self):
        doc = {"text": "test"}
        scrubbed = {"text": "@PERSON_1"}
        response_body = {"document": scrubbed, "redactions": [], "registry": {}}
        success_resp = _make_response(response_body)
        http_503 = _make_http_error(503, retry_after="1")

        call_count = [0]
        def _urlopen_side_effect(req, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise http_503
            return success_resp

        with patch("canvas_tui.pii.urllib.request.urlopen", side_effect=_urlopen_side_effect):
            with patch("canvas_tui.pii.time.sleep") as mock_sleep:
                result = scrub_via_space(doc, "https://example.hf.space")

        assert result == scrubbed
        assert call_count[0] == 2
        mock_sleep.assert_called_once()

    def test_retry_exhausted_falls_back(self):
        """If retry also fails (503 again), fall back to local scrub."""
        doc = {"text": "Hello"}
        http_503 = _make_http_error(503, retry_after="1")

        with patch("canvas_tui.pii.urllib.request.urlopen", side_effect=http_503):
            with patch("canvas_tui.pii.time.sleep"):
                with patch("canvas_tui.pii.scrub_doc", return_value={"text": "fallback"}) as mock_scrub:
                    result = scrub_via_space(doc, "https://example.hf.space")

        assert result == {"text": "fallback"}
        mock_scrub.assert_called_once()


class TestNetworkErrorFallback:
    """Test 4: URLError — fall back to local scrub_doc."""

    def test_url_error_falls_back_to_local(self):
        doc = {"text": "Hello world"}
        url_err = urllib.error.URLError("Connection refused")

        with patch("canvas_tui.pii.urllib.request.urlopen", side_effect=url_err):
            with patch("canvas_tui.pii.scrub_doc", return_value={"text": "local_result"}) as mock_scrub:
                result = scrub_via_space(doc, "https://example.hf.space")

        assert result == {"text": "local_result"}
        mock_scrub.assert_called_once()

    def test_url_error_prints_warning(self, capsys):
        doc = {"text": "Hello"}
        url_err = urllib.error.URLError("Connection refused")

        with patch("canvas_tui.pii.urllib.request.urlopen", side_effect=url_err):
            with patch("canvas_tui.pii.scrub_doc", return_value=doc):
                scrub_via_space(doc, "https://example.hf.space")

        captured = capsys.readouterr()
        assert "fallback" in captured.err.lower() or "warning" in captured.err.lower() or "error" in captured.err.lower()


class TestScrubMethodKwarg:
    """Test 5: scrub_doc scrub_method='space' kwarg dispatches to scrub_via_space."""

    def test_scrub_method_space_calls_urlopen(self):
        doc = {"text": "test"}
        response_body = {"document": doc, "redactions": [], "registry": {}}
        mock_resp = _make_response(response_body)

        with patch("canvas_tui.pii.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            scrub_doc(doc, scrub_method="space", space_url="http://mock")

        mock_open.assert_called_once()

    def test_scrub_method_local_piiranha_no_urlopen(self):
        """Default scrub_method='local-piiranha' must not call urlopen."""
        doc = {"text": "test"}
        with patch("canvas_tui.pii.urllib.request.urlopen") as mock_open:
            scrub_doc(doc)
        mock_open.assert_not_called()


class TestScrubMethodMissingUrl:
    """Test 6: scrub_doc with scrub_method='space' and no space_url raises ValueError."""

    def test_missing_space_url_raises_value_error(self):
        with pytest.raises(ValueError, match="space_url"):
            scrub_doc({"text": "x"}, scrub_method="space")


class TestCanvasPiiSpaceUrlConstant:
    """CANVAS_PII_SPACE_URL must be exported and have the correct default."""

    def test_canvas_pii_space_url_exported(self):
        assert CANVAS_PII_SPACE_URL is not None
        assert isinstance(CANVAS_PII_SPACE_URL, str)
        assert "hf.space" in CANVAS_PII_SPACE_URL or "kleinpanic93" in CANVAS_PII_SPACE_URL
