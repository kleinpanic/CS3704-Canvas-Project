"""PM4 tests for Canvas API: token validation and planner fetch."""
import json
from unittest.mock import MagicMock, patch

import pytest

from canvas_tui.api import CanvasAPI


def _make_response(status=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or []
    resp.headers = headers or {}
    resp.raise_for_status.return_value = None
    return resp


class TestTokenValidation:
    def setup_method(self):
        self.api = CanvasAPI(token="test-token", base_url="https://canvas.example.com")

    @patch("canvas_tui.api.requests.Session")
    def test_valid_token_returns_true(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(status=200, json_data={"id": 1})
        mock_session_cls.return_value = session
        api = CanvasAPI(token="valid-token", base_url="https://canvas.example.com")
        assert api.validate_token() is True

    @patch("canvas_tui.api.requests.Session")
    def test_invalid_token_returns_false(self, mock_session_cls):
        session = MagicMock()
        resp = _make_response(status=401)
        resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        session.get.return_value = resp
        mock_session_cls.return_value = session
        api = CanvasAPI(token="bad-token", base_url="https://canvas.example.com")
        assert api.validate_token() is False

    @patch("canvas_tui.api.requests.Session")
    def test_network_error_returns_false(self, mock_session_cls):
        import requests
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("unreachable")
        mock_session_cls.return_value = session
        api = CanvasAPI(token="any-token", base_url="https://canvas.example.com")
        assert api.validate_token() is False

    @patch("canvas_tui.api.requests.Session")
    def test_authorization_header_contains_bearer_token(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(status=200, json_data={"id": 1})
        mock_session_cls.return_value = session
        api = CanvasAPI(token="my-secret-token", base_url="https://canvas.example.com")
        api.validate_token()
        call_kwargs = session.get.call_args
        # Headers may be set at session level or per-request; check either
        headers_used = (
            call_kwargs[1].get("headers", {})
            if call_kwargs and call_kwargs[1]
            else {}
        )
        auth_header = (
            headers_used.get("Authorization", "")
            or session.headers.get("Authorization", "")
        )
        assert "Bearer" in auth_header
        assert "my-secret-token" in auth_header


class TestPlannerFetch:
    @patch("canvas_tui.api.requests.Session")
    def test_fetch_returns_items_from_api(self, mock_session_cls, sample_planner_items):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=sample_planner_items)
        mock_session_cls.return_value = session
        api = CanvasAPI(token="tok", base_url="https://canvas.example.com")
        result = api.fetch_planner_items()
        assert len(result) == len(sample_planner_items)

    @patch("canvas_tui.api.requests.Session")
    def test_fetch_empty_list_when_no_assignments(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=[])
        mock_session_cls.return_value = session
        api = CanvasAPI(token="tok", base_url="https://canvas.example.com")
        result = api.fetch_planner_items()
        assert result == []

    @patch("canvas_tui.api.requests.Session")
    def test_pagination_follows_link_header(self, mock_session_cls):
        page1 = _make_response(
            json_data=[{"id": 1}],
            headers={"Link": '<https://canvas.example.com/page2>; rel="next"'},
        )
        page2 = _make_response(json_data=[{"id": 2}], headers={})
        session = MagicMock()
        session.get.side_effect = [page1, page2]
        mock_session_cls.return_value = session
        api = CanvasAPI(token="tok", base_url="https://canvas.example.com")
        result = api.fetch_planner_items()
        assert len(result) == 2
        assert session.get.call_count == 2

    @patch("canvas_tui.api.requests.Session")
    def test_fetch_uses_stale_cache_when_offline(self, mock_session_cls, tmp_dir, sample_planner_items):
        import requests
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("offline")
        mock_session_cls.return_value = session

        api = CanvasAPI(token="tok", base_url="https://canvas.example.com", cache_dir=tmp_dir)
        # Pre-populate stale cache manually
        cache_key = api._cache.cache_key("/api/v1/planner/items", {})
        api._cache.put(cache_key, sample_planner_items)

        result = api.fetch_planner_items()
        assert result == sample_planner_items

    @patch("canvas_tui.api.requests.Session")
    def test_date_window_passed_as_query_params(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=[])
        mock_session_cls.return_value = session
        api = CanvasAPI(token="tok", base_url="https://canvas.example.com")
        api.fetch_planner_items(start_date="2026-04-01", end_date="2026-04-30")
        call_url = session.get.call_args[0][0]
        params = session.get.call_args[1].get("params", {})
        assert "start_date" in params or "start_date" in call_url
        assert "end_date" in params or "end_date" in call_url