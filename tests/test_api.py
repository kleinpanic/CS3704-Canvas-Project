"""PM4 tests for Canvas API: token validation and planner fetch."""
from unittest.mock import MagicMock, call, patch

import pytest

from canvas_tui.api import CanvasAPI
from canvas_tui.cache import ResponseCache, cache_key
from canvas_tui.config import Config


def _cfg(token="test-token", base_url="https://canvas.example.com"):
    """Build a minimal Config for tests."""
    return Config(token=token, base_url=base_url)


def _make_response(status=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data if json_data is not None else []
    resp.headers = headers or {}
    resp.raise_for_status.return_value = None
    return resp


class TestTokenValidation:
    """Tests for CanvasAPI.validate_token() — covers Issue #18 (Canvas authentication)."""

    @patch("canvas_tui.api.requests.Session")
    def test_valid_token_returns_true(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(status=200, json_data={"id": 1})
        mock_session_cls.return_value = session
        api = CanvasAPI(cfg=_cfg(token="valid-token"))
        assert api.validate_token() is True

    @patch("canvas_tui.api.requests.Session")
    def test_invalid_token_returns_false(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(status=401)
        mock_session_cls.return_value = session
        api = CanvasAPI(cfg=_cfg(token="bad-token"))
        assert api.validate_token() is False

    @patch("canvas_tui.api.requests.Session")
    def test_network_error_returns_false(self, mock_session_cls):
        import requests
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("unreachable")
        mock_session_cls.return_value = session
        api = CanvasAPI(cfg=_cfg(token="any-token"))
        assert api.validate_token() is False

    @patch("canvas_tui.api.requests.Session")
    def test_authorization_header_contains_bearer_token(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(status=200, json_data={"id": 1})
        mock_session_cls.return_value = session
        api = CanvasAPI(cfg=_cfg(token="my-secret-token"))
        api.validate_token()
        # Authorization header is set on the session via headers.update() in _build_session()
        update_calls = session.headers.update.call_args_list
        assert update_calls, "session.headers.update was never called"
        merged = {}
        for c in update_calls:
            merged.update(c[0][0] if c[0] else c[1])
        assert "Authorization" in merged
        assert merged["Authorization"] == "Bearer my-secret-token"


class TestPlannerFetch:
    """Tests for CanvasAPI.fetch_planner_items() — covers Feature 2 (Canvas Synchronization)."""

    @patch("canvas_tui.api.requests.Session")
    def test_fetch_returns_items_from_api(self, mock_session_cls, sample_planner_items):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=sample_planner_items)
        mock_session_cls.return_value = session
        api = CanvasAPI(cfg=_cfg())
        result = api.fetch_planner_items()
        assert len(result) == len(sample_planner_items)

    @patch("canvas_tui.api.requests.Session")
    def test_fetch_empty_list_when_no_assignments(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=[])
        mock_session_cls.return_value = session
        api = CanvasAPI(cfg=_cfg())
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
        api = CanvasAPI(cfg=_cfg())
        result = api.fetch_planner_items()
        assert len(result) == 2
        assert session.get.call_count == 2

    @patch("canvas_tui.api.requests.Session")
    def test_fetch_uses_stale_cache_when_offline(self, mock_session_cls, tmp_dir, sample_planner_items):
        import requests
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("offline")
        mock_session_cls.return_value = session

        rc = ResponseCache(tmp_dir)
        api = CanvasAPI(cfg=_cfg(), response_cache=rc)

        # Pre-populate cache with planner data so stale fallback can find it
        ck = cache_key("planner_items", {"per_page": 100, "start_date": mock_session_cls.ANY, "end_date": mock_session_cls.ANY})
        # Use the key the API will actually generate by calling _cached_get_all indirectly;
        # instead, prime every possible key by storing under the real computed key.
        # Easiest: write directly to cache for the key the API will compute.
        import datetime as _dt
        from zoneinfo import ZoneInfo
        from canvas_tui.api import _iso
        from canvas_tui.cache import cache_key as _ck
        cfg = _cfg()
        tz = ZoneInfo(cfg.user_tz)
        now = _dt.datetime.now(tz)
        start = _iso(now - _dt.timedelta(hours=cfg.past_hours))
        end = _iso((now + _dt.timedelta(days=cfg.days_ahead)).replace(hour=23, minute=59, second=59, microsecond=0))
        params = {"start_date": start, "end_date": end, "per_page": 100}
        real_key = _ck("planner_items", params)
        rc.put(real_key, sample_planner_items)

        result = api.fetch_planner_items()
        assert result == sample_planner_items

    @patch("canvas_tui.api.requests.Session")
    def test_date_window_passed_as_query_params(self, mock_session_cls):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=[])
        mock_session_cls.return_value = session
        api = CanvasAPI(cfg=_cfg())
        api.fetch_planner_items()
        # fetch_planner_items builds start_date/end_date from cfg and passes as params
        assert session.get.called
        params = session.get.call_args[1].get("params", {})
        assert "start_date" in params
        assert "end_date" in params
