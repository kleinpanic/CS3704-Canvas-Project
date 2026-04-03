"""
Cache prefetch helpers for startup performance.
Used by CLI prefetch modes to warm API response cache + state cache
without launching the TUI.
"""

from __future__ import annotations

import contextlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .api import CanvasAPI
from .cache import ResponseCache
from .config import Config, ensure_dirs
from .normalize import apply_past_filter, normalize_announcements, normalize_items, serialize_items
from .state import StateManager


def prefetch_once(cfg: Config, *, no_cache: bool = False, include_grades: bool = True) -> dict[str, Any]:
    """Warm caches with a single fetch pass.

    Returns metrics dict suitable for CLI display.
    """
    ensure_dirs(cfg)
    # Set dir
    response_cache = ResponseCache(cache_dir=f"{cfg.export_dir}/cache", default_ttl=900)
    api = CanvasAPI(cfg, response_cache=response_cache)
    api._no_cache = no_cache
    state = StateManager(cfg.state_path)

    t0 = time.perf_counter()

    course_cache, course_scores = api.fetch_course_snapshot()

    planner_raw = api.fetch_planner_items()
    all_items = normalize_items(planner_raw, api, cfg.user_tz)
    items = apply_past_filter(all_items, cfg.past_hours, cfg.user_tz)

    ann_raw: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        ann_raw = api.fetch_announcements(list(course_cache.keys()))
    announcements = normalize_announcements(ann_raw, course_cache, cfg.base_url, cfg.user_tz)

    # Keep startup fast even offline by persisting normalized state cache.
    state.update_cache(serialize_items(items), serialize_items(announcements))

    warmed_grade_courses = 0
    if include_grades and course_cache:
        course_ids = list(course_cache.keys())
        max_workers = max(2, min(8, len(course_ids)))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="prefetch-grades") as ex:
            fut_map = {ex.submit(api.fetch_grades, cid): cid for cid in course_ids}
            for fut in as_completed(fut_map):
                with contextlib.suppress(Exception):
                    _ = fut.result()
                    warmed_grade_courses += 1

    elapsed = round(time.perf_counter() - t0, 2)
    return {
        "elapsed_sec": elapsed,
        "items": len(items),
        "announcements": len(announcements),
        "courses": len(course_cache),
        "course_scores": len(course_scores),
        "grade_courses_warmed": warmed_grade_courses,
        "offline": api.is_offline,
    }


def prefetch_daemon_loop(
    cfg: Config,
    *,
    interval_sec: int = 300,
    no_cache: bool = False,
    include_grades: bool = True,
) -> None:
    """Run prefetch forever on a fixed interval (for user services)."""
    interval = max(60, int(interval_sec))
    while True:
        try:
            metrics = prefetch_once(cfg, no_cache=no_cache, include_grades=include_grades)
            print(
                "prefetch:"
                f" {metrics['elapsed_sec']}s"
                f" items={metrics['items']}"
                f" anns={metrics['announcements']}"
                f" courses={metrics['courses']}"
                f" grade_warm={metrics['grade_courses_warmed']}"
                f" offline={metrics['offline']}"
            )
        except Exception as exc:  # pragma: no cover (CLI-side resilience)
            print(f"prefetch error: {exc}")
        time.sleep(interval)
