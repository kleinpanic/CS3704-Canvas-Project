"""Normalization — convert raw Canvas API responses to CanvasItem objects."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo

from .api import CanvasAPI
from .models import CanvasItem
from .utils import absolute_url, fmt_local, legacy_item_key, local_dt, rel_time, stable_item_key


def best_due(pl: dict[str, Any], ptype: str) -> str | None:
    """Pick the first available date field from a plannable."""
    for k in (
        "due_at",
        "lock_at",
        "todo_date",
        "start_at",
        "end_at",
        "published_at",
        "posted_at",
        "created_at",
        "available_at",
    ):
        v = pl.get(k)
        if v:
            return v
    return None


def normalize_items(
    raw: list[dict[str, Any]],
    api: CanvasAPI,
    tz: str = "America/New_York",
) -> list[CanvasItem]:
    """Normalize raw planner items into CanvasItem objects.

    Uses batch course cache to avoid N+1 queries.
    """
    # Build course cache from all unique course_ids in one pass
    course_ids = sorted({x.get("course_id") for x in raw if x.get("course_id")})
    course_cache: dict[int, tuple[str, str]] = {}
    # Batch fetch via current courses endpoint (one call)
    try:
        all_courses = api.fetch_current_courses()
        course_cache.update(all_courses)
    except Exception:
        pass
    # Fill any missing courses individually (rare edge case)
    for cid in course_ids:
        if cid not in course_cache:
            try:
                course_cache[cid] = api.fetch_course_name(int(cid))
            except Exception:
                course_cache[cid] = ("", "")

    out: list[CanvasItem] = []
    for x in raw:
        ptype = (x.get("plannable_type") or "").lower()
        pl = x.get("plannable") or {}
        if ptype == "discussion_topic" and (
            pl.get("is_announcement") or x.get("is_announcement") or pl.get("announcement")
        ):
            ptype = "announcement"

        due_iso = best_due(pl, ptype) or ""
        due_local = fmt_local(due_iso, tz) if due_iso else ""
        rel = rel_time(local_dt(due_iso, tz), tz) if due_iso else ""
        course_id = x.get("course_id")
        course_code, course_name = course_cache.get(course_id, ("", ""))

        sub = x.get("submissions")
        flags: list[str] = []
        if isinstance(sub, dict):
            for flag in (
                "missing",
                "late",
                "graded",
                "excused",
                "submitted",
                "with_feedback",
                "needs_grading",
            ):
                if sub.get(flag) is True:
                    flags.append(flag)

        url_abs = absolute_url(x.get("html_url", "/"), api.cfg.base_url)
        points = pl.get("points_possible") if ptype == "assignment" else None
        title = pl.get("title") or pl.get("name") or "(untitled)"

        item = CanvasItem(
            key=stable_item_key(course_id, x.get("plannable_id"), ptype),
            legacy_key=legacy_item_key(course_id, x.get("plannable_id"), ptype, title),
            ptype=ptype,
            title=title,
            course_code=course_code or str(course_id or ""),
            course_name=course_name,
            due_at=due_local,
            due_rel=rel,
            due_iso=due_iso,
            url=url_abs,
            course_id=course_id,
            plannable_id=x.get("plannable_id"),
            points=points,
            status_flags=flags,
            raw_plannable=pl,
        )
        out.append(item)

    def sortkey(it: CanvasItem) -> dt.datetime:
        try:
            return dt.datetime.strptime(it.due_at, "%m/%d/%Y %H:%M")
        except Exception:
            return dt.datetime.max

    out.sort(key=sortkey)
    return out


def normalize_announcements(
    raw: list[dict[str, Any]],
    course_cache: dict[int, tuple[str, str]],
    base_url: str,
    tz: str = "America/New_York",
) -> list[CanvasItem]:
    """Normalize raw announcements into CanvasItem objects."""
    out: list[CanvasItem] = []
    for a in raw:
        course_id = a.get("course_id")
        if not course_id:
            m = re.search(r"course_(\d+)", str(a.get("context_code", "")))
            if m:
                course_id = int(m.group(1))

        code, name = course_cache.get(course_id, ("", ""))  # type: ignore[arg-type]
        title = a.get("title") or (a.get("message") or "").strip()[:60] or "(announcement)"
        ts = a.get("posted_at") or a.get("delayed_post_at") or a.get("created_at") or ""
        url_abs = absolute_url(a.get("html_url") or a.get("url") or "/", base_url)

        item = CanvasItem(
            key=stable_item_key(course_id, a.get("id"), "announcement"),
            ptype="announcement",
            title=title,
            course_code=code or str(course_id or ""),
            course_name=name,
            due_at=fmt_local(ts, tz) if ts else "",
            due_rel=rel_time(local_dt(ts, tz), tz) if ts else "",
            due_iso=ts,
            url=url_abs,
            course_id=course_id,
            plannable_id=a.get("id"),
            points=None,
            status_flags=[],
            raw_plannable=a,
        )
        out.append(item)

    def sortkey(it: CanvasItem) -> dt.datetime:
        try:
            return dt.datetime.strptime(it.due_at, "%m/%d/%Y %H:%M")
        except Exception:
            return dt.datetime.min

    out.sort(key=sortkey, reverse=True)
    return out


def apply_past_filter(
    items: list[CanvasItem],
    past_hours: int,
    tz: str = "America/New_York",
) -> list[CanvasItem]:
    """Filter out old/submitted items. Single implementation — no duplication."""
    now = dt.datetime.now(ZoneInfo(tz))
    cutoff = now - dt.timedelta(hours=past_hours)
    out: list[CanvasItem] = []
    for it in items:
        if it.ptype in ("announcement", "calendar_event", "planner_note"):
            continue
        rp = it.raw_plannable or {}
        ts_iso = it.due_iso or rp.get("posted_at") or rp.get("created_at") or rp.get("available_at") or ""
        if not ts_iso:
            out.append(it)
            continue
        ts = local_dt(ts_iso, tz)

        # Skip locked+missing items
        lock_at = rp.get("lock_at")
        if lock_at:
            try:
                if "missing" in it.status_flags and local_dt(lock_at, tz) < now:
                    continue
            except Exception:
                pass

        if ts >= cutoff:
            # Skip past submitted items
            if ts < now and "submitted" in it.status_flags:
                continue
            out.append(it)
    return out


def serialize_items(items: list[CanvasItem]) -> list[dict[str, Any]]:
    """Serialize items for cache storage."""
    return [it.to_dict() for it in items]
