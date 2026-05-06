# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for canvas_sdk.client.CanvasClient.
All HTTP is mocked via unittest.mock.patch on urllib.request.urlopen.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure the SDK source is importable when running from repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "sdk"))

import urllib.error

from canvas_sdk.client import CanvasClient
from canvas_sdk.entities import Course
from canvas_sdk.exceptions import (
    CanvasServerError,
    Conflict,
    Forbidden,
    InvalidAccessToken,
    RateLimitExceeded,
    ResourceNotFound,
    UnprocessableEntity,
)

TOKEN = "supersecrettoken"
BASE_URL = "https://canvas.example.edu"


def _make_response(body: object, headers: dict | None = None, status: int = 200):
    """Return a mock suitable for use as the urllib.request.urlopen context manager."""
    raw = json.dumps(body).encode()
    hdr = {"content-type": "application/json"}
    if headers:
        hdr.update({k.lower(): v for k, v in headers.items()})

    mock_resp = MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.status = status
    mock_resp.headers = MagicMock()
    mock_resp.headers.items.return_value = list(hdr.items())
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_http_error(status: int, body: object):
    """Return an HTTPError whose .read() returns the JSON-encoded body."""
    raw = json.dumps(body).encode()
    hdrs = MagicMock()
    hdrs.items.return_value = []
    exc = urllib.error.HTTPError(
        url="https://canvas.example.edu/api/v1/test",
        code=status,
        msg="Error",
        hdrs=hdrs,
        fp=io.BytesIO(raw),
    )
    return exc


def _client() -> CanvasClient:
    c = CanvasClient(BASE_URL, TOKEN)
    c._sleep = MagicMock()  # prevent real sleeps in retry tests
    return c


class TestAuthHeader(unittest.TestCase):
    """Authorization header is correctly set on every request."""

    def test_bearer_token_in_request(self):
        client = _client()
        mock_resp = _make_response({"id": 1, "name": "Test User"})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            client.get_current_user()

        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TOKEN}")

    def test_token_not_in_repr_of_exception(self):
        client = _client()
        with patch(
            "urllib.request.urlopen",
            side_effect=_make_http_error(401, {"errors": [{"message": "Invalid token"}]}),
        ):
            with self.assertRaises(InvalidAccessToken) as ctx:
                client.get_current_user()

        exc = ctx.exception
        self.assertNotIn(TOKEN, repr(exc))
        self.assertNotIn(TOKEN, str(exc))
        for arg in exc.args:
            self.assertNotIn(TOKEN, str(arg))


class TestPagination(unittest.TestCase):
    """Pagination follows Link rel=next and aggregates results from all pages."""

    def test_follows_next_link(self):
        page1_items = [{"id": 1, "name": "Course A"}]
        page2_items = [{"id": 2, "name": "Course B"}]

        resp1 = _make_response(
            page1_items,
            headers={"Link": f'<{BASE_URL}/api/v1/courses?page=2>; rel="next"'},
        )
        resp2 = _make_response(page2_items, headers={})

        client = _client()
        with patch("urllib.request.urlopen", side_effect=[resp1, resp2]):
            courses = client.get_courses()

        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0].id, 1)
        self.assertEqual(courses[1].id, 2)

    def test_single_page_no_link(self):
        client = _client()
        resp = _make_response([{"id": 42, "name": "Only Course"}])
        with patch("urllib.request.urlopen", return_value=resp):
            courses = client.get_courses()

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].name, "Only Course")


class TestErrorMapping(unittest.TestCase):
    """HTTP status codes map to the correct exception classes."""

    def _assert_raises(self, status: int, exc_class):
        client = _client()
        body = {"errors": [{"message": f"HTTP {status} error"}]}
        with patch(
            "urllib.request.urlopen",
            side_effect=_make_http_error(status, body),
        ):
            with self.assertRaises(exc_class):
                client.get_current_user()

    def test_401_raises_invalid_access_token(self):
        self._assert_raises(401, InvalidAccessToken)

    def test_403_raises_forbidden(self):
        self._assert_raises(403, Forbidden)

    def test_404_raises_resource_not_found(self):
        self._assert_raises(404, ResourceNotFound)

    def test_409_raises_conflict(self):
        self._assert_raises(409, Conflict)

    def test_422_raises_unprocessable_entity(self):
        self._assert_raises(422, UnprocessableEntity)

    def test_500_raises_canvas_server_error(self):
        client = _client()
        body = {"errors": [{"message": "Internal Server Error"}]}
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                _make_http_error(500, body),
                _make_http_error(500, body),
                _make_http_error(500, body),
                _make_http_error(500, body),
            ],
        ):
            with self.assertRaises(CanvasServerError):
                client.get_current_user()


class TestRetry429(unittest.TestCase):
    """429 triggers retries; exception raised after retries exhausted."""

    def test_429_retried_then_raised(self):
        client = _client()
        body = {"errors": [{"message": "Rate limit exceeded"}]}
        side_effects = [_make_http_error(429, body) for _ in range(4)]

        with patch("urllib.request.urlopen", side_effect=side_effects):
            with self.assertRaises(RateLimitExceeded):
                client.get_current_user()

        # 3 retries means sleep called 3 times (after each of the first 3 failures)
        self.assertEqual(client._sleep.call_count, 3)

    def test_429_succeeds_on_retry(self):
        client = _client()
        rate_err = _make_http_error(429, {"errors": [{"message": "rate limit"}]})
        success = _make_response({"id": 7, "name": "user"})

        with patch("urllib.request.urlopen", side_effect=[rate_err, success]):
            user = client.get_current_user()

        self.assertEqual(user.id, 7)
        client._sleep.assert_called_once()


class TestIncludeParamEncoding(unittest.TestCase):
    """include[] is encoded with doseq=True so multiple values produce repeated keys."""

    def test_include_array_repeated_keys(self):
        client = _client()
        resp = _make_response([])
        captured_url = []

        def fake_urlopen(req, timeout=None):
            captured_url.append(req.full_url)
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.get_courses(include=["syllabus_body", "term"])

        self.assertTrue(captured_url, "urlopen was never called")
        url = captured_url[0]
        self.assertIn("include%5B%5D=syllabus_body", url)
        self.assertIn("include%5B%5D=term", url)

    def test_context_codes_repeated_keys(self):
        client = _client()
        resp = _make_response([])
        captured_url = []

        def fake_urlopen(req, timeout=None):
            captured_url.append(req.full_url)
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.get_announcements(context_codes=["course_1", "course_2"])

        url = captured_url[0]
        self.assertIn("context_codes%5B%5D=course_1", url)
        self.assertIn("context_codes%5B%5D=course_2", url)


class TestExtraFieldsIgnored(unittest.TestCase):
    """Unknown fields on Course (and other entities) do not raise."""

    def test_extra_fields_stored_not_raised(self):
        client = _client()
        course_data = {
            "id": 99,
            "name": "Test Course",
            "course_code": "TST101",
            "unknown_future_canvas_field": "some_value",
            "another_new_field": 12345,
        }
        resp = _make_response([course_data])

        with patch("urllib.request.urlopen", return_value=resp):
            courses = client.get_courses()

        self.assertEqual(len(courses), 1)
        c = courses[0]
        self.assertEqual(c.id, 99)
        self.assertEqual(c.name, "Test Course")
        self.assertIn("unknown_future_canvas_field", c.extra_fields)
        self.assertEqual(c.extra_fields["unknown_future_canvas_field"], "some_value")
        self.assertIn("another_new_field", c.extra_fields)

    def test_from_api_classmethod(self):
        data = {"id": 5, "name": "X", "mystery": True}
        c = Course.from_api(data)
        self.assertEqual(c.id, 5)
        self.assertEqual(c.extra_fields["mystery"], True)


class TestTokenNotLeaked(unittest.TestCase):
    """Token must not appear in any exception message, repr, or args."""

    def _get_exc(self, status: int) -> Exception:
        client = _client()
        body = {"errors": [{"message": "access denied"}]}
        with patch(
            "urllib.request.urlopen",
            side_effect=_make_http_error(status, body),
        ):
            try:
                client.get_current_user()
            except Exception as exc:
                return exc
        return AssertionError("no exception raised")

    def test_token_not_in_401(self):
        exc = self._get_exc(401)
        self.assertNotIn(TOKEN, str(exc))
        self.assertNotIn(TOKEN, repr(exc))

    def test_token_not_in_403(self):
        exc = self._get_exc(403)
        self.assertNotIn(TOKEN, str(exc))
        self.assertNotIn(TOKEN, repr(exc))

    def test_token_not_in_404(self):
        exc = self._get_exc(404)
        self.assertNotIn(TOKEN, str(exc))
        self.assertNotIn(TOKEN, repr(exc))


class TestUrlConstruction(unittest.TestCase):
    """base_url and endpoint paths are correctly joined."""

    def test_no_double_slash(self):
        client = CanvasClient("https://canvas.example.edu/", TOKEN)
        client._sleep = MagicMock()
        resp = _make_response({"id": 1})
        captured = []

        def fake(req, timeout=None):
            captured.append(req.full_url)
            return resp

        with patch("urllib.request.urlopen", side_effect=fake):
            client.get_current_user()

        self.assertTrue(captured[0].startswith("https://canvas.example.edu/api/v1/users/self"))
        self.assertNotIn("//api", captured[0])

    def test_course_id_in_path(self):
        client = _client()
        resp = _make_response([])
        captured = []

        def fake(req, timeout=None):
            captured.append(req.full_url)
            return resp

        with patch("urllib.request.urlopen", side_effect=fake):
            client.get_assignments(42)

        self.assertIn("/api/v1/courses/42/assignments", captured[0])


if __name__ == "__main__":
    unittest.main()
