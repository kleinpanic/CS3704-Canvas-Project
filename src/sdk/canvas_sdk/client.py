# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator, Optional

from canvas_sdk.entities import (
    Assignment,
    Course,
    DiscussionTopic,
    Enrollment,
    PlannerNote,
    Todo,
    User,
)
from canvas_sdk.exceptions import (
    CanvasException,
    CanvasServerError,
    Conflict,
    Forbidden,
    InvalidAccessToken,
    RateLimitExceeded,
    ResourceNotFound,
    UnprocessableEntity,
)

_MAX_PER_PAGE = 100
_MAX_RETRIES = 3
_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def _parse_canvas_error(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            messages = [e.get("message", "") for e in errors if isinstance(e, dict)]
            return "; ".join(m for m in messages if m)
        if isinstance(errors, str):
            return errors
    except Exception:
        pass
    return body.decode("utf-8", errors="replace")[:200]


def _map_http_error(status: int, body: bytes, path: str) -> CanvasException:
    detail = _parse_canvas_error(body)
    msg = f"HTTP {status} for {path}: {detail}" if detail else f"HTTP {status} for {path}"
    if status == 401:
        return InvalidAccessToken(msg)
    if status == 403:
        return Forbidden(msg)
    if status == 404:
        return ResourceNotFound(msg)
    if status == 409:
        return Conflict(msg)
    if status == 422:
        return UnprocessableEntity(msg)
    if status == 429:
        return RateLimitExceeded(msg)
    if status >= 500:
        return CanvasServerError(msg)
    return CanvasException(msg)


class CanvasClient:
    """A read-only client for the Canvas LMS API (stdlib urllib, no third-party deps)."""

    def __init__(self, base_url: str, access_token: str, *, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token
        self._timeout = timeout
        self._sleep = time.sleep
        self.latest_request_cost: Optional[float] = None
        self.rate_limit_remaining: Optional[float] = None

    def _build_url(self, path: str, params: Optional[dict] = None) -> str:
        url = self._base_url + path
        if params:
            pairs = []
            for key, value in params.items():
                if value is None:
                    continue
                if isinstance(value, list):
                    for item in value:
                        pairs.append((key, str(item)))
                elif isinstance(value, bool):
                    pairs.append((key, "true" if value else "false"))
                else:
                    pairs.append((key, str(value)))
            if pairs:
                url = url + "?" + urllib.parse.urlencode(pairs, doseq=True)
        return url

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    def _raw_get(self, url: str) -> tuple[bytes, dict]:
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return body, headers
        except urllib.error.HTTPError as exc:
            body = exc.read()
            raise exc.__class__(
                exc.url, exc.code, exc.msg, exc.headers, None
            ) from None

    def _get_with_retry(self, url: str) -> tuple[bytes, dict]:
        last_exc: Optional[urllib.error.HTTPError] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                body, headers = self._raw_get(url)
                cost_str = headers.get("x-request-cost")
                remaining_str = headers.get("x-rate-limit-remaining")
                if cost_str is not None:
                    try:
                        self.latest_request_cost = float(cost_str)
                    except ValueError:
                        pass
                if remaining_str is not None:
                    try:
                        self.rate_limit_remaining = float(remaining_str)
                    except ValueError:
                        pass
                return body, headers
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status in (429,) or (500 <= status < 600):
                    last_exc = exc
                    if attempt < _MAX_RETRIES:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                        self._sleep(delay)
                        continue
                    body = exc.read() if hasattr(exc, "read") else b""
                    path = urllib.parse.urlparse(url).path
                    raise _map_http_error(status, body, path)
                else:
                    body = exc.read() if hasattr(exc, "read") else b""
                    path = urllib.parse.urlparse(url).path
                    raise _map_http_error(status, body, path)
        body = last_exc.read() if last_exc and hasattr(last_exc, "read") else b""
        path = urllib.parse.urlparse(url).path
        raise _map_http_error(last_exc.code if last_exc else 500, body, path)

    def _parse_next_link(self, link_header: Optional[str]) -> Optional[str]:
        if not link_header:
            return None
        m = _LINK_NEXT_RE.search(link_header)
        return m.group(1) if m else None

    def _paginate(self, url: str) -> Iterator[dict]:
        next_url: Optional[str] = url
        while next_url:
            body, headers = self._get_with_retry(next_url)
            items = json.loads(body)
            if not isinstance(items, list):
                yield items
                return
            for item in items:
                yield item
            next_url = self._parse_next_link(headers.get("link"))

    def _get_single(self, path: str, params: Optional[dict] = None) -> dict:
        url = self._build_url(path, params)
        body, _ = self._get_with_retry(url)
        return json.loads(body)

    def _get_list(self, path: str, params: Optional[dict] = None) -> list[dict]:
        url = self._build_url(path, params)
        return list(self._paginate(url))

    def get_current_user(self) -> User:
        data = self._get_single("/api/v1/users/self")
        return User.from_api(data)

    def get_courses(
        self,
        *,
        enrollment_state: Optional[str] = None,
        include: Optional[list] = None,
        per_page: int = 100,
    ) -> list[Course]:
        per_page = min(per_page, _MAX_PER_PAGE)
        params: dict = {"per_page": per_page}
        if enrollment_state is not None:
            params["enrollment_state"] = enrollment_state
        if include:
            params["include[]"] = include
        items = self._get_list("/api/v1/courses", params)
        return [Course.from_api(d) for d in items]

    def get_course(self, course_id: int, *, include: Optional[list] = None) -> Course:
        params: dict = {}
        if include:
            params["include[]"] = include
        data = self._get_single(f"/api/v1/courses/{course_id}", params or None)
        return Course.from_api(data)

    def get_assignments(
        self,
        course_id: int,
        *,
        bucket: Optional[str] = None,
        include: Optional[list] = None,
        per_page: int = 100,
    ) -> list[Assignment]:
        per_page = min(per_page, _MAX_PER_PAGE)
        params: dict = {"per_page": per_page}
        if bucket is not None:
            params["bucket"] = bucket
        if include:
            params["include[]"] = include
        items = self._get_list(f"/api/v1/courses/{course_id}/assignments", params)
        return [Assignment.from_api(d) for d in items]

    def get_enrollments(
        self,
        course_id: int,
        *,
        user_id: Optional[str] = None,
        include: Optional[list] = None,
    ) -> list[Enrollment]:
        params: dict = {"per_page": _MAX_PER_PAGE}
        if user_id is not None:
            params["user_id"] = user_id
        if include:
            params["include[]"] = include
        items = self._get_list(f"/api/v1/courses/{course_id}/enrollments", params)
        return [Enrollment.from_api(d) for d in items]

    def get_discussion_topics(
        self,
        course_id: int,
        *,
        only_announcements: bool = False,
    ) -> list[DiscussionTopic]:
        params: dict = {"per_page": _MAX_PER_PAGE}
        if only_announcements:
            params["only_announcements"] = True
        items = self._get_list(
            f"/api/v1/courses/{course_id}/discussion_topics", params
        )
        return [DiscussionTopic.from_api(d) for d in items]

    def get_modules(self, course_id: int) -> list[dict]:
        params: dict = {"per_page": _MAX_PER_PAGE}
        return self._get_list(f"/api/v1/courses/{course_id}/modules", params)

    def get_files(self, course_id: int) -> list[dict]:
        params: dict = {"per_page": _MAX_PER_PAGE}
        return self._get_list(f"/api/v1/courses/{course_id}/files", params)

    def get_announcements(
        self,
        *,
        context_codes: list,
        start_date: Optional[str] = None,
    ) -> list[DiscussionTopic]:
        params: dict = {"per_page": _MAX_PER_PAGE, "context_codes[]": context_codes}
        if start_date is not None:
            params["start_date"] = start_date
        items = self._get_list("/api/v1/announcements", params)
        return [DiscussionTopic.from_api(d) for d in items]

    def get_todo_items(self) -> list[Todo]:
        items = self._get_list("/api/v1/users/self/todo", {"per_page": _MAX_PER_PAGE})
        return [Todo.from_api(d) for d in items]

    def get_planner_notes(self) -> list[PlannerNote]:
        items = self._get_list("/api/v1/planner_notes", {"per_page": _MAX_PER_PAGE})
        return [PlannerNote.from_api(d) for d in items]

    def get_upcoming_events(self) -> list[dict]:
        url = self._build_url("/api/v1/users/self/upcoming_events")
        body, _ = self._get_with_retry(url)
        result = json.loads(body)
        if isinstance(result, list):
            return result
        return [result]
