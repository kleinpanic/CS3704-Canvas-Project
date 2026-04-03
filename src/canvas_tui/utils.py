"""Utility functions for Canvas TUI — date parsing, HTML stripping, filesystem helpers."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from zoneinfo import ZoneInfo


def course_label(code: str, max_len: int = 12) -> str:
    """Normalize a course code for display labels.

    Truncates to max_len, strips trailing underscores/whitespace.
    """
    label = code[:max_len].rstrip("_ ")
    return label or code[:max_len]


class _HTMLStripper(HTMLParser):
    """Robust HTML-to-text converter using html.parser instead of regex."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("br", "p", "div", "li", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False
        elif tag in ("p", "div", "table"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        from html import unescape

        self._parts.append(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        from html import unescape

        self._parts.append(unescape(f"&#{name};"))

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def strip_html(html: str) -> str:
    """Strip HTML tags robustly, converting to plain text."""
    if not html:
        return ""
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
        return stripper.get_text()
    except Exception:
        # Fallback: regex strip (lossy but safe)
        return re.sub(r"<[^>]+>", "", html)


def local_dt(iso_str: str, tz: str = "America/New_York") -> dt.datetime:
    """Parse ISO 8601 string to timezone-aware local datetime."""
    return dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))


def fmt_local(ts_iso: str, tz: str = "America/New_York") -> str:
    """Format ISO timestamp as human-readable local time."""
    t = local_dt(ts_iso, tz)
    try:
        return t.strftime("%-m/%-d/%Y %H:%M")  # Linux
    except ValueError:
        return t.strftime("%m/%d/%Y %H:%M")


def rel_time(target: dt.datetime, tz: str = "America/New_York") -> str:
    """Compute relative time string (e.g. 'in 2d 3h' or '5h 10m ago')."""
    now = dt.datetime.now(ZoneInfo(tz))
    total_seconds = int((target - now).total_seconds())
    sign = 1 if total_seconds >= 0 else -1
    s = abs(total_seconds)
    d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60

    if sign > 0:
        if d > 0:
            return f"in {d}d {h}h"
        if h > 0:
            return f"in {h}h {m}m"
        return f"in {m}m"
    else:
        if d > 0:
            return f"{d}d {h}h ago"
        if h > 0:
            return f"{h}h {m}m ago"
        return f"{m}m ago"


def sanitize_filename(s: str) -> str:
    """Make a string safe for use as a file name."""
    s = re.sub(r'[\\/:\*\?"<>\|]+', "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "untitled"


def absolute_url(html_url: str, base_url: str) -> str:
    """Make a URL absolute relative to base."""
    if html_url.startswith(("http://", "https://")):
        return html_url
    from urllib.parse import urljoin

    return urljoin(base_url, html_url)


def get_download_dir(override: str | None = None) -> str:
    """Resolve download directory (override > XDG > ~/Downloads)."""
    if override:
        return os.path.expanduser(override)
    xdg = os.path.expanduser("~/.config/user-dirs.dirs")
    if os.path.exists(xdg):
        with open(xdg, encoding="utf-8") as f:
            for line in f:
                if line.startswith("XDG_DOWNLOAD_DIR"):
                    val = line.split("=", 1)[1].strip().strip('"')
                    val = val.replace("$HOME", os.path.expanduser("~"))
                    return val
    return os.path.expanduser("~/Downloads")


def notify(summary: str, body: str = "") -> None:
    """Send desktop notification or terminal bell."""
    if shutil.which("notify-send"):
        with contextlib.suppress(Exception):
            subprocess.Popen(["notify-send", summary, body])
    else:
        with contextlib.suppress(Exception):
            print("\a", end="", flush=True)


def stable_item_key(course_id: int | None, plannable_id: int | None, ptype: str) -> str:
    """Generate a stable unique key for a planner item."""
    cid = str(int(course_id)) if course_id else ""
    pid = str(int(plannable_id)) if plannable_id else ""
    return f"{cid}:{pid}:{(ptype or '').lower()}"


def legacy_item_key(course_id: int | None, plannable_id: int | None, ptype: str, title: str) -> str:
    """Generate legacy key format for migration."""
    return f"{course_id}:{plannable_id}:{ptype}:{abs(hash(title))}"


def open_url(url: str) -> None:
    """Open URL in the user's graphical browser.

    Prefers xdg-open (Linux) or open (macOS) over Python's webbrowser
    module, which may fall back to w3m or lynx in terminal environments.
    """
    import platform
    import subprocess
    import webbrowser

    if not url:
        return

    system = platform.system()
    try:
        if system == "Linux":
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        elif system == "Darwin":
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            webbrowser.open(url, new=2)
    except FileNotFoundError:
        webbrowser.open(url, new=2)
