"""ICS (iCalendar) export for Canvas TUI — extracted from app.py for reuse."""

from __future__ import annotations

import datetime as dt
import os
import socket
from zoneinfo import ZoneInfo

from .config import Config
from .models import CanvasItem
from .utils import local_dt


def ics_escape(s: str) -> str:
    """Escape special ICS characters."""
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_dt(ts: dt.datetime) -> str:
    """Format datetime as ICS UTC timestamp."""
    return ts.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def item_to_vevent(it: CanvasItem, cfg: Config) -> str | None:
    """Convert a CanvasItem to a VEVENT string. Returns None if no due date."""
    if not it.due_iso:
        return None

    due = local_dt(it.due_iso, cfg.user_tz)
    start = due - dt.timedelta(minutes=cfg.default_block_min)
    uid = f"canvas-{it.course_id or ''}-{it.plannable_id or ''}-{abs(hash(it.title))}@{socket.gethostname()}"
    summary = f"{it.course_code} • {it.title} [{it.ptype}]"
    desc = f"URL: {it.url}"
    loc = it.course_name or it.course_code
    now_str = ics_dt(dt.datetime.now(ZoneInfo(cfg.user_tz)))

    return "\n".join(
        [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_str}",
            f"DTSTART:{ics_dt(start)}",
            f"DTEND:{ics_dt(due)}",
            f"SUMMARY:{ics_escape(summary)}",
            f"DESCRIPTION:{ics_escape(desc)}",
            f"LOCATION:{ics_escape(loc)}",
            "END:VEVENT",
        ]
    )


def export_ics(items: list[CanvasItem], cfg: Config, path: str | None = None) -> str:
    """Export all items to an ICS file. Returns the file path."""
    out_path = path or cfg.export_ics_path
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    events = [item_to_vevent(it, cfg) for it in items]
    ics_body = "\n".join(e for e in events if e)

    ics_content = f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//canvas-tui//EN\n{ics_body}\nEND:VCALENDAR\n"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    return out_path
