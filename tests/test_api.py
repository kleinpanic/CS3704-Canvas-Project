"""PM4 tests for Canvas API: token validation and planner fetch."""
from unittest.mock import MagicMock, patch

import pytest

from canvas_tui.api import CanvasAPI, _iso
from canvas_tui.cache import ResponseCache, cache_key
from canvas_tui.config import Config


def _make_response(status=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or []
    resp.headers = headers or {}
    resp.raise_for_status.return_value = None
    return resp


class TestTokenValidation:
    def setup_method(self):
        cfg = Config(token="test-token", base_url="https://canvas.example.com")
        self.api = CanvasAPI(cfg=cfg)

    @patch("canvas_tui.api.requests.Session")
    def test_valid_token_returns_true(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(status=200, json_data={"id": 1})
        mock_session_cls.return_value = session
        cfg = Config(token="valid-token", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
        assert api.validate_token() is True

    @patch("canvas_tui.api.requests.Session")
    def test_invalid_token_returns_false(self, mock_session_cls):
        session = MagicMock()
        resp = _make_response(status=401)
        resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        session.get.return_value = resp
        mock_session_cls.return_value = session
        cfg = Config(token="bad-token", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
        assert api.validate_token() is False

    @patch("canvas_tui.api.requests.Session")
    def test_network_error_returns_false(self, mock_session_cls):
        import requests
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("unreachable")
        mock_session_cls.return_value = session
        cfg = Config(token="any-token", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
        assert api.validate_token() is False

    @patch("canvas_tui.api.requests.Session")
    def test_authorization_header_contains_bearer_token(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session
        cfg = Config(token="my-secret-token", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
        # Verify session was created and initialized with Bearer auth header
        assert mock_session_cls.called
        # The auth header is stored in api.cfg.token — verify it's correctly set
        assert api.cfg.token == "my-secret-token"
        # Verify the session.headers received the Authorization header
        auth_calls = session.headers.update.call_args_list
        assert len(auth_calls) >= 1
        # Check the auth header value from the most recent update call
        latest_update = auth_calls[-1]
        headers_dict = latest_update[0][0]
        assert headers_dict["Authorization"] == "Bearer my-secret-token"


class TestPlannerFetch:
    @patch("canvas_tui.api.requests.Session")
    def test_fetch_returns_items_from_api(self, mock_session_cls, sample_planner_items):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=sample_planner_items)
        mock_session_cls.return_value = session
        cfg = Config(token="tok", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
        result = api.fetch_planner_items()
        assert len(result) == len(sample_planner_items)

    @patch("canvas_tui.api.requests.Session")
    def test_fetch_empty_list_when_no_assignments(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=[])
        mock_session_cls.return_value = session
        cfg = Config(token="tok", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
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
        cfg = Config(token="tok", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
        result = api.fetch_planner_items()
        assert len(result) == 2
        assert session.get.call_count == 2

    def test_fetch_uses_stale_cache_when_offline(self, tmp_dir, sample_planner_items):
        """Offline + stale cache → returns stale data, sets _offline=True."""
        import requests
        import datetime as dt

        # Patch _build_session so we control the session without patching requests.Session globally
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.ConnectionError("offline")

        cfg = Config(token="tok", base_url="https://canvas.example.com")
        cache = ResponseCache(cache_dir=tmp_dir)
        api = CanvasAPI(cfg=cfg, response_cache=cache)
        # Inject the mock session directly — bypasses _build_session entirely
        api._session = mock_session

        # Pre-populate stale cache (entry older than TTL)
        now = dt.datetime.now()
        start = _iso(now - dt.timedelta(hours=72))
        end = _iso((now + dt.timedelta(days=7)).replace(hour=23, minute=59, second=59))
        ck = cache_key("planner_items", {"start_date": start, "end_date": end, "per_page": 100})
        cache.put(ck, sample_planner_items)

        result = api.fetch_planner_items()
        assert result == sample_planner_items

    @patch("canvas_tui.api.requests.Session")
    def test_date_window_passed_as_query_params(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=[])
        mock_session_cls.return_value = session
        cfg = Config(token="tok", base_url="https://canvas.example.com")
        api = CanvasAPI(cfg=cfg)
        api.fetch_planner_items()
        params = session.get.call_args[1].get("params", {})
        assert "start_date" in params
        assert "end_date" in params