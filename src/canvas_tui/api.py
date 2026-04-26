"""Canvas LMS API client with retry, rate-limit awareness, and pagination."""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import ResponseCache, cache_key
from .config import Config


class CanvasAPI:
    """Canvas LMS REST API client.

    Handles authentication, pagination, retries, rate-limit headers, and caching.
    """

    def __init__(self, cfg: Config, response_cache: ResponseCache | None = None) -> None:
        self.cfg = cfg
        self._session = self._build_session()
        self._rate_limit_remaining: int | None = None
        self._cache = response_cache
        self._offline = False
        self._no_cache = False

    def _build_session(self) -> requests.Session:
        """Create a requests session with retry and auth headers."""
        s = requests.Session()
        s.headers.update(
            {
                "Authorization": f"Bearer {self.cfg.token}",
                "User-Agent": self.cfg.user_agent,
                "Accept": "application/json",
            }
        )
        retry = Retry(
            total=self.cfg.max_retries,
            connect=self.cfg.max_retries,
            read=self.cfg.max_retries,
            backoff_factor=self.cfg.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    @property
    def session(self) -> requests.Session:
        """Expose the underlying session for direct downloads."""
        return self._session

    @property
    def rate_limit_remaining(self) -> int | None:
        """Last known rate limit remaining count."""
        return self._rate_limit_remaining

    def _update_rate_limit(self, response: requests.Response) -> None:
        """Parse X-Rate-Limit-Remaining from Canvas API response."""
        val = response.headers.get("X-Rate-Limit-Remaining")
        if val is not None:
            with contextlib.suppress(ValueError, TypeError):
                self._rate_limit_remaining = int(float(val))

    def _url(self, path: str) -> str:
        """Build absolute API URL."""
        return urljoin(self.cfg.base_url, path)

    @staticmethod
    def _parse_link_header(link_value: str) -> dict[str, str]:
        """Parse Link header for pagination."""
        out: dict[str, str] = {}
        if not link_value:
            return out
        for part in link_value.split(","):
            part = part.strip()
            if ";" not in part:
                continue
            url_part, *params = part.split(";")
            url = url_part.strip().lstrip("<").rstrip(">")
            rel = None
            for p in params:
                if "rel=" in p:
                    rel = p.split("=", 1)[1].strip().strip('"')
                    break
            if rel:
                out[rel] = url
        return out

    @property
    def is_offline(self) -> bool:
        """Whether last fetch fell back to stale cache."""
        return self._offline

    def _cached_get_all(self, ck: str, url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """get_all with cache layer. On network failure, returns stale cache."""
        if self._cache and not self._no_cache:
            cached, stale = self._cache.get(ck, allow_stale=True)
            if cached is not None:
                self._offline = False
                return cached

        try:
            data = self.get_all(url, params)
            self._offline = False
            if self._cache and not self._no_cache:
                self._cache.put(ck, data)
            return data
        except Exception:
            # Network failure — try stale cache
            if self._cache:
                cached, _ = self._cache.get(ck, allow_stale=True)
                if cached is not None:
                    self._offline = True
                    return cached
            raise

    def get_all(self, url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Walk paginated Canvas API endpoint."""
        items: list[dict[str, Any]] = []
        params = dict(params or {})
        while True:
            r = self._session.get(url, params=params, timeout=self.cfg.http_timeout)
            self._update_rate_limit(r)
            if r.status_code == 401:
                raise SystemExit("Unauthorized (401). Check CANVAS_TOKEN.")
            r.raise_for_status()
            page = r.json()
            if not page:
                pass
            elif isinstance(page, list):
                items.extend(page)
            else:
                items.append(page)
            links = self._parse_link_header(r.headers.get("Link", ""))
            if "next" in links:
                url = links["next"]
                params = {}
            else:
                break
        return items

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Single GET returning JSON or None on error."""
        try:
            r = self._session.get(url, params=params or {}, timeout=self.cfg.http_timeout)
            self._update_rate_limit(r)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ---------- High-level Canvas endpoints ----------

    def fetch_planner_items(self) -> list[dict[str, Any]]:
        """Fetch planner items in the configured date window (cached)."""
        tz = ZoneInfo(self.cfg.user_tz)
        now = dt.datetime.now(tz)
        start = _iso(now - dt.timedelta(hours=self.cfg.past_hours))
        end = _iso((now + dt.timedelta(days=self.cfg.days_ahead)).replace(hour=23, minute=59, second=59, microsecond=0))
        params = {"start_date": start, "end_date": end, "per_page": 100}
        ck = cache_key("planner_items", params)
        return self._cached_get_all(ck, self._url("/api/v1/planner/items"), params)

    def fetch_course_snapshot(self) -> tuple[dict[int, tuple[str, str]], dict[int, float]]:
        """Fetch active courses and Canvas-computed scores in one API pass (cached).

        Returns:
            (courses, scores)
            - courses: {course_id: (course_code, course_name)}
            - scores: {course_id: computed_current_score}
        """
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
                for k in (
                    "computed_current_score",
                    "current_score",
                    "computed_final_score",
                    "final_score",
                ):
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
        """Fetch active courses (cached). Returns {course_id: (code, name)}."""
        courses, _ = self.fetch_course_snapshot()
        return courses

    def fetch_course_scores(self, course_ids: set[int] | None = None) -> dict[int, float]:
        """Fetch Canvas-computed current scores per course (cached)."""
        _, scores = self.fetch_course_snapshot()
        if not course_ids:
            return scores
        return {cid: score for cid, score in scores.items() if cid in course_ids}

    def fetch_course_name(self, course_id: int) -> tuple[str, str]:
        """Fetch course code and name for a single course."""
        data = self.get_json(self._url(f"/api/v1/courses/{course_id}"))
        if data:
            return data.get("course_code") or "", data.get("name") or ""
        return "", ""

    def fetch_assignment_details(self, course_id: int, assignment_id: int) -> dict[str, Any]:
        """Fetch full assignment details."""
        r = self._session.get(
            self._url(f"/api/v1/courses/{course_id}/assignments/{assignment_id}"),
            timeout=self.cfg.http_timeout,
        )
        self._update_rate_limit(r)
        r.raise_for_status()
        return r.json()

    def fetch_submission(self, course_id: int, assignment_id: int) -> dict[str, Any] | None:
        """Fetch user's submission for an assignment."""
        return self.get_json(self._url(f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self"))

    def fetch_discussion(self, course_id: int, topic_id: int) -> dict[str, Any] | None:
        """Fetch a discussion topic or announcement."""
        return self.get_json(
            self._url(f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}"),
            {"include[]": ["all_dates", "sections", "sections_user_count"]},
        )

    def fetch_course_syllabus(self, course_id: int) -> str | None:
        """Fetch HTML syllabus body for a course."""
        data = self.get_json(
            self._url(f"/api/v1/courses/{course_id}"),
            {"include[]": "syllabus_body"},
        )
        if data:
            return data.get("syllabus_body")
        return None

    def search_course_files(self, course_id: int, term: str) -> list[dict[str, Any]]:
        """Search files in a course by term."""
        try:
            return self.get_all(
                self._url(f"/api/v1/courses/{course_id}/files"),
                {"search_term": term, "per_page": 50},
            )
        except Exception:
            return []

    def fetch_announcements(self, course_ids: list[int]) -> list[dict[str, Any]]:
        """Fetch announcements in the configured date window (cached)."""
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
        """Fetch assignment groups (with weights) for a course."""
        try:
            return self.get_all(
                self._url(f"/api/v1/courses/{course_id}/assignment_groups"),
                {"per_page": 100},
            )
        except Exception:
            return []

    def fetch_course_info(self, course_id: int) -> dict[str, Any] | None:
        """Fetch extended course info with teacher, term, and enrollment count."""
        return self.get_json(
            self._url(f"/api/v1/courses/{course_id}"),
            {"include[]": ["teachers", "term", "total_students"]},
        )

    def fetch_grades(self, course_id: int) -> list[dict[str, Any]]:
        """Fetch all assignments with grades for a course (cached)."""
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
        """Lightweight token validation — hits /api/v1/users/self."""
        data = self.get_json(self._url("/api/v1/users/self"))
        return data is not None


def _iso(ts: dt.datetime) -> str:
    """Format datetime as ISO 8601 UTC string for Canvas API."""
    return ts.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
