"""Background due date notification system."""

from __future__ import annotations

import contextlib
import datetime as dt
import threading
import time
from collections.abc import Callable
from zoneinfo import ZoneInfo

from .models import CanvasItem
from .utils import local_dt, notify


class DueNotifier:
    """Background thread that watches for upcoming due dates and sends notifications.

    Configurable alert thresholds (e.g., 1h, 30m, 15m before).
    """

    DEFAULT_THRESHOLDS_MIN = [60, 30, 15]

    def __init__(
        self,
        tz: str = "America/New_York",
        thresholds_min: list[int] | None = None,
        get_items: Callable[[], list[CanvasItem]] | None = None,
    ) -> None:
        self._tz = tz
        self._thresholds = sorted(thresholds_min or self.DEFAULT_THRESHOLDS_MIN, reverse=True)
        self._get_items = get_items
        self._notified: set[str] = set()  # "key:threshold" pairs already notified
        self._thread: threading.Thread | None = None
        self._stop = False

    def start(self) -> None:
        """Start the notification background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the notification thread."""
        self._stop = True

    def _run(self) -> None:
        """Main notification loop — checks every 60s."""
        while not self._stop:
            with contextlib.suppress(Exception):
                self._check()
            for _ in range(60):
                if self._stop:
                    return
                time.sleep(1)

    def _check(self) -> None:
        """Check all items against thresholds."""
        if not self._get_items:
            return
        items = self._get_items()
        now = dt.datetime.now(ZoneInfo(self._tz))

        for it in items:
            if not it.due_iso:
                continue
            if "submitted" in it.status_flags:
                continue
            try:
                due = local_dt(it.due_iso, self._tz)
            except Exception:
                continue

            minutes_until = (due - now).total_seconds() / 60.0
            if minutes_until < 0:
                continue

            for threshold in self._thresholds:
                nkey = f"{it.key}:{threshold}"
                if nkey in self._notified:
                    continue
                if minutes_until <= threshold:
                    self._notified.add(nkey)
                    _send_notification(it, threshold)
                    break  # Only fire the first matching threshold

    def clear_notified(self) -> None:
        """Clear notification history (e.g., on refresh)."""
        self._notified.clear()


def _send_notification(it: CanvasItem, threshold_min: int) -> None:
    """Send a desktop notification for an upcoming due date."""
    if threshold_min >= 60:
        time_str = f"{threshold_min // 60}h"
    else:
        time_str = f"{threshold_min}m"

    summary = f"⏰ Due in {time_str}: {it.title}"
    body = f"{it.course_code} — {it.ptype}"
    notify(summary, body)
