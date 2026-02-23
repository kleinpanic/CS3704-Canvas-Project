"""CLI argument parser for Canvas TUI."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        prog="canvas-tui",
        description="Canvas LMS TUI client — planner, announcements, syllabi, downloads, grades, pomodoro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
environment variables:
  CANVAS_TOKEN        Canvas API access token (required)
  CANVAS_BASE_URL     Canvas instance URL (default: https://canvas.vt.edu)
  TZ                  Timezone (default: America/New_York)
  DAYS_AHEAD          Days to look ahead (default: 7)
  PAST_HOURS          Hours to look back (default: 72)
  HTTP_TIMEOUT        HTTP timeout in seconds (default: 20)

examples:
  canvas-tui                      Launch TUI
  canvas-tui --export-ics         Export items to ICS and exit
  canvas-tui --no-cache           Launch without disk cache
  canvas-tui --debug              Show debug info on startup
""",
    )

    p.add_argument(
        "-V", "--version",
        action="version",
        version=f"canvas-tui {__version__}",
    )
    p.add_argument(
        "-c", "--config",
        metavar="PATH",
        help="Path to config file (TOML or JSON)",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable disk response cache",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    p.add_argument(
        "--export-ics",
        action="store_true",
        help="Export all items to ICS file and exit (no TUI)",
    )
    p.add_argument(
        "--theme",
        choices=["dark", "light"],
        default="dark",
        help="Color theme (default: dark)",
    )
    p.add_argument(
        "--days-ahead",
        type=int,
        metavar="N",
        help="Override DAYS_AHEAD",
    )
    p.add_argument(
        "--past-hours",
        type=int,
        metavar="N",
        help="Override PAST_HOURS",
    )

    return p.parse_args(argv)


def handle_non_tui_commands(args: argparse.Namespace) -> bool:
    """Handle commands that don't need the TUI. Returns True if handled."""
    if args.export_ics:
        _export_ics_and_exit(args)
        return True
    return False


def _export_ics_and_exit(args: argparse.Namespace) -> None:
    """Export ICS without launching TUI."""
    from .api import CanvasAPI
    from .config import ensure_dirs, load_config
    from .normalize import apply_past_filter, normalize_items

    cfg = load_config()
    if args.config:
        cfg.config_dir = args.config
    if args.days_ahead is not None:
        cfg.days_ahead = args.days_ahead
    if args.past_hours is not None:
        cfg.past_hours = args.past_hours
    ensure_dirs(cfg)

    api = CanvasAPI(cfg)
    print(f"Fetching planner items from {cfg.base_url}…")
    raw = api.fetch_planner_items()
    items = normalize_items(raw, api, cfg.user_tz)
    items = apply_past_filter(items, cfg.past_hours, cfg.user_tz)

    # Minimal ICS export
    import datetime as dt
    import os
    import socket
    from zoneinfo import ZoneInfo

    from .utils import local_dt

    events = []
    for it in items:
        if not it.due_iso:
            continue
        due = local_dt(it.due_iso, cfg.user_tz)
        start = due - dt.timedelta(minutes=cfg.default_block_min)

        def ics_dt(ts: dt.datetime) -> str:
            return ts.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")

        uid = f"canvas-{it.course_id or ''}-{it.plannable_id or ''}-{abs(hash(it.title))}@{socket.gethostname()}"
        events.append(
            f"BEGIN:VEVENT\n"
            f"UID:{uid}\n"
            f"DTSTAMP:{ics_dt(dt.datetime.now(ZoneInfo(cfg.user_tz)))}\n"
            f"DTSTART:{ics_dt(start)}\n"
            f"DTEND:{ics_dt(due)}\n"
            f"SUMMARY:{it.course_code} • {it.title} [{it.ptype}]\n"
            f"DESCRIPTION:URL: {it.url}\n"
            f"END:VEVENT"
        )

    ics_path = cfg.export_ics_path
    os.makedirs(os.path.dirname(ics_path), exist_ok=True)
    with open(ics_path, "w", encoding="utf-8") as f:
        f.write("BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//canvas-tui//EN\n")
        for e in events:
            f.write(e + "\n")
        f.write("END:VCALENDAR\n")

    print(f"Exported {len(events)} events to {ics_path}")
    sys.exit(0)
