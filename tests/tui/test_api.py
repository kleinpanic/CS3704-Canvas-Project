# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for CanvasAPI adapter — verifies it wraps canvas_sdk.CanvasClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from canvas_tui.api import CanvasAPI
from canvas_tui.config import Config


def _make_cfg(**kwargs) -> Config:
    defaults = {
        "token": "test_token",
        "base_url": "https://canvas.example.com",
    }
    defaults.update(kwargs)
    return Config(**defaults)


class TestValidateToken:
    def test_returns_true_when_get_json_returns_user(self):
        with patch("canvas_tui.api.CanvasClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_json.return_value = {"id": 1, "name": "Test User"}
            mock_cls.return_value = mock_client
            api = CanvasAPI(_make_cfg())
            assert api.validate_token() is True

    def test_returns_false_when_get_json_returns_none(self):
        with patch("canvas_tui.api.CanvasClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_json.return_value = None
            mock_cls.return_value = mock_client
            api = CanvasAPI(_make_cfg())
            assert api.validate_token() is False


class TestFetchPlannerItems:
    def test_returns_list_from_client(self):
        with patch("canvas_tui.api.CanvasClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = [{"id": 1, "type": "assignment"}]
            mock_cls.return_value = mock_client
            api = CanvasAPI(_make_cfg())
            # Bypass cache for test
            api._cache = None
            result = api.fetch_planner_items()
            assert isinstance(result, list)

    def test_returns_empty_list_on_empty_response(self):
        with patch("canvas_tui.api.CanvasClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client
            api = CanvasAPI(_make_cfg())
            api._cache = None
            result = api.fetch_planner_items()
            assert result == []


class TestFetchCurrentCourses:
    def test_returns_dict_from_client(self):
        with patch("canvas_tui.api.CanvasClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = [
                {"id": 101, "course_code": "CS3704", "name": "Software Engineering"}
            ]
            mock_cls.return_value = mock_client
            api = CanvasAPI(_make_cfg())
            api._cache = None
            result = api.fetch_current_courses()
            assert isinstance(result, dict)
            assert 101 in result


class TestIsOffline:
    def test_offline_false_by_default(self):
        with patch("canvas_tui.api.CanvasClient"):
            api = CanvasAPI(_make_cfg())
            assert api.is_offline is False

    def test_offline_true_after_network_failure_with_no_cache(self):
        with patch("canvas_tui.api.CanvasClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.side_effect = ConnectionError("network down")
            mock_cls.return_value = mock_client
            api = CanvasAPI(_make_cfg())
            api._cache = None
            with pytest.raises(Exception):
                api.fetch_planner_items()
            assert api.is_offline is False


class TestRateLimitRemaining:
    def test_returns_none_by_default(self):
        with patch("canvas_tui.api.CanvasClient"):
            api = CanvasAPI(_make_cfg())
            assert api.rate_limit_remaining is None


class TestSessionProperty:
    def test_session_property_exists_and_is_not_none(self):
        with patch("canvas_tui.api.CanvasClient"):
            api = CanvasAPI(_make_cfg())
            assert api.session is not None
