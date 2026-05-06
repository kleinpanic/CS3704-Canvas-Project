# SPDX-License-Identifier: GPL-3.0-or-later
"""Canvas LMS API adapter — delegates HTTP to canvas_sdk.CanvasClient."""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from canvas_sdk.client import CanvasClient

from .cache import ResponseCache, cache_key
from .config import Config


class CanvasAPI:
    """Thin adapter wrapping canvas_sdk.CanvasClient.

    Pagination, retry, and rate-limiting are delegated to CanvasClient.
    This adapter adds: caching layer, offline fallback, and the high-level
    Canvas-domain methods the TUI calls.
    """

    def __init__(self, cfg: Config, response_cache: ResponseCache | None = None) -> None:
        self.cfg = cfg
        self._client = CanvasClient(cfg.base_url, cfg.token)
        self._cache = response_cache
        self._offline = False
        self._no_cache = False
        # Separate session for binary downloads (CanvasClient handles JSON only)
        self._download_session = self._build_download_session()

    def _build_download_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(
            {
                "Authorization": f"Bearer {self.cfg.token}",
                "User-Agent": self.cfg.user_agent,
            }
        )
        return s

    @property
    def session(self) -> requests.Session:
        """Expose a session for direct binary downloads."""
        return self._download_session

    @property
    def rate_limit_remaining(self) -> int | None:
        # SDK does not expose rate limit counter yet; always None.
        return None

    @property
    def is_offline(self) -> bool:
        return self._offline

    def _url(self, path: str) -> str:
        return urljoin(self.cfg.base_url, path)

    def _cached_get_all(self, ck: str, url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if self._cache and not self._no_cache:
            cached, stale = self._cache.get(ck, allow_stale=True)
            if cached is not None and not stale:
                self._offline = False
                return cached

        try:
            data = self._client.get_all(url, params)
            self._offline = False
            if self._cache and not self._no_cache:
                self._cache.put(ck, data)
            return data
        except Exception:
            if self._cache:
                cached, _ = self._cache.get(ck, allow_stale=True)
                if cached is not None:
                    self._offline = True
                    return cached
            raise

    def get_all(self, url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._client.get_all(url, params)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._client.get_json(url, params)

    # ---------- High-level Canvas endpoints ----------

    def fetch_planner_items(self) -> list[dict[str, Any]]:
        tz = ZoneInfo(self.cfg.user_tz)
        now = dt.datetime.now(tz)
        start = _iso(now - dt.timedelta(hours=self.cfg.past_hours))
        end = _iso((now + dt.timedelta(days=self.cfg.days_ahead)).replace(hour=23, minute=59, second=59, microsecond=0))
        params = {"start_date": start, "end_date": end, "per_page": 100}
        ck = cache_key("planner_items", params)
        return self._cached_get_all(ck, self._url("/api/v1/planner/items"), params)

    def fetch_course_snapshot(self) -> tuple[dict[int, tuple[str, str]], dict[int, float]]:
        params: dict[str, Any] = {
            "enrollment_state": "active",
            "include[]": ["total_scores"],
            "per_page": 100,
        }
        ck = cache_key("courses_snapshot", params)
        raw = self._cached_get_all(ck, self._url("/api/v1/courses"), params)

        courses: dict[int, tuple[str, str]] = {}
        scores: dict[int, float] = {}

        for c in raw:
            cid = c.get("id")
            if not cid:
                continue
            cid_i = int(cid)
            courses[cid_i] = (c.get("course_code") or str(cid), c.get("name") or "")

            enrollments = c.get("enrollments") if isinstance(c.get("enrollments"), list) else []
            score: float | None = None
            for e in enrollments:
                if not isinstance(e, dict):
                    continue
                for k in ("computed_current_score", "current_score", "computed_final_score", "final_score"):
                    v = e.get(k)
                    if isinstance(v, (int, float)):
                        score = float(v)
                        break
                if score is not None:
                    break

            if score is not None:
                scores[cid_i] = score

        return courses, scores

    def fetch_current_courses(self) -> dict[int, tuple[str, str]]:
        courses, _ = self.fetch_course_snapshot()
        return courses

    def fetch_course_scores(self, course_ids: set[int] | None = None) -> dict[int, float]:
        _, scores = self.fetch_course_snapshot()
        if not course_ids:
            return scores
        return {cid: score for cid, score in scores.items() if cid in course_ids}

    def fetch_course_name(self, course_id: int) -> tuple[str, str]:
        data = self.get_json(self._url(f"/api/v1/courses/{course_id}"))
        if data:
            return data.get("course_code") or "", data.get("name") or ""
        return "", ""

    def fetch_assignment_details(self, course_id: int, assignment_id: int) -> dict[str, Any]:
        r = self._download_session.get(
            self._url(f"/api/v1/courses/{course_id}/assignments/{assignment_id}"),
            timeout=self.cfg.http_timeout,
        )
        r.raise_for_status()
        return r.json()

    def fetch_submission(self, course_id: int, assignment_id: int) -> dict[str, Any] | None:
        return self.get_json(self._url(f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self"))

    def fetch_discussion(self, course_id: int, topic_id: int) -> dict[str, Any] | None:
        return self.get_json(
            self._url(f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}"),
            {"include[]": ["all_dates", "sections", "sections_user_count"]},
        )

    def fetch_course_syllabus(self, course_id: int) -> str | None:
        data = self.get_json(
            self._url(f"/api/v1/courses/{course_id}"),
            {"include[]": "syllabus_body"},
        )
        if data:
            return data.get("syllabus_body")
        return None

    def search_course_files(self, course_id: int, term: str) -> list[dict[str, Any]]:
        try:
            return self.get_all(
                self._url(f"/api/v1/courses/{course_id}/files"),
                {"search_term": term, "per_page": 50},
            )
        except Exception:
            return []

    def fetch_announcements(self, course_ids: list[int]) -> list[dict[str, Any]]:
        if not course_ids:
            return []
        tz = ZoneInfo(self.cfg.user_tz)
        now = dt.datetime.now(tz)
        start = _iso(now - dt.timedelta(days=self.cfg.ann_past_days))
        end = _iso(
            (now + dt.timedelta(days=self.cfg.ann_future_days)).replace(hour=23, minute=59, second=59, microsecond=0)
        )
        params: dict[str, Any] = {
            "start_date": start,
            "end_date": end,
            "per_page": 100,
        }
        params["context_codes[]"] = [f"course_{cid}" for cid in sorted(course_ids)]
        ck = cache_key("announcements", params)
        return self._cached_get_all(ck, self._url("/api/v1/announcements"), params)

    def fetch_assignment_groups(self, course_id: int) -> list[dict[str, Any]]:
        try:
            return self.get_all(
                self._url(f"/api/v1/courses/{course_id}/assignment_groups"),
                {"per_page": 100},
            )
        except Exception:
            return []

    def fetch_course_info(self, course_id: int) -> dict[str, Any] | None:
        return self.get_json(
            self._url(f"/api/v1/courses/{course_id}"),
            {"include[]": ["teachers", "term", "total_students"]},
        )

    def fetch_grades(self, course_id: int) -> list[dict[str, Any]]:
        params = {"per_page": 100, "include[]": ["submission"]}
        ck = cache_key(f"grades:{course_id}", params)
        try:
            return self._cached_get_all(
                ck,
                self._url(f"/api/v1/courses/{course_id}/assignments"),
                params,
            )
        except Exception:
            return []

    def validate_token(self) -> bool:
        data = self.get_json(self._url("/api/v1/users/self"))
        return data is not None


def _iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
