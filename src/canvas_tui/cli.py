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
  CANVAS_ASCII        Set to 1 to use ASCII-only charts (auto-enabled on Windows)

examples:
  canvas-tui                              Launch TUI
  canvas-tui --export-ics                 Export items to ICS and exit
  canvas-tui --prefetch                   Warm caches and exit (no TUI)
  canvas-tui --prefetch-daemon            Run lightweight prefetch loop
  canvas-tui --no-cache                   Launch without disk cache
  canvas-tui --debug                      Show debug info on startup
""",
    )

    p.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"canvas-tui {__version__}",
    )
    p.add_argument(
        "-c",
        "--config",
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
        "--validate-token",
        action="store_true",
        help="Validate Canvas API token and exit",
    )
    p.add_argument(
        "--prefetch",
        action="store_true",
        help="Warm caches/state and exit (no TUI)",
    )
    p.add_argument(
        "--prefetch-daemon",
        action="store_true",
        help="Run continuous prefetch loop for background cache warming",
    )
    p.add_argument(
        "--prefetch-interval",
        type=int,
        default=300,
        metavar="SEC",
        help="Prefetch daemon interval seconds (default: 300)",
    )
    p.add_argument(
        "--prefetch-no-grades",
        action="store_true",
        help="Skip grade endpoint warming in prefetch mode",
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
    if args.validate_token:
        _validate_token_and_exit()
        return True
    if args.prefetch:
        _prefetch_and_exit(args)
        return True
    if args.prefetch_daemon:
        _prefetch_daemon(args)
        return True
    return False


def _validate_token_and_exit() -> None:
    """Validate token and exit."""
    from .api import CanvasAPI
    from .config import load_config

    cfg = load_config()
    api = CanvasAPI(cfg)
    print(f"Validating token against {cfg.base_url}…")
    if api.validate_token():
        print("OK: Token is valid!")
        sys.exit(0)
    else:
        print("FAIL: Token validation failed. Check CANVAS_TOKEN and CANVAS_BASE_URL.")
        sys.exit(1)


def _prefetch_and_exit(args: argparse.Namespace) -> None:
    """Warm caches/state and exit."""
    from .config import load_config
    from .prefetch import prefetch_once

    cfg = load_config()
    if args.config:
        cfg.config_dir = args.config
    if args.days_ahead is not None:
        cfg.days_ahead = args.days_ahead
    if args.past_hours is not None:
        cfg.past_hours = args.past_hours

    metrics = prefetch_once(
        cfg,
        no_cache=args.no_cache,
        include_grades=not args.prefetch_no_grades,
    )
    print(
        f"Prefetch complete in {metrics['elapsed_sec']}s | "
        f"items={metrics['items']} announcements={metrics['announcements']} "
        f"courses={metrics['courses']} grade_warm={metrics['grade_courses_warmed']} "
        f"offline={metrics['offline']}"
    )
    sys.exit(0)


def _prefetch_daemon(args: argparse.Namespace) -> None:
    """Run prefetch daemon loop."""
    from .config import load_config
    from .prefetch import prefetch_daemon_loop

    cfg = load_config()
    if args.config:
        cfg.config_dir = args.config
    if args.days_ahead is not None:
        cfg.days_ahead = args.days_ahead
    if args.past_hours is not None:
        cfg.past_hours = args.past_hours

    print(
        f"Starting prefetch daemon (interval={args.prefetch_interval}s, include_grades={not args.prefetch_no_grades})"
    )
    prefetch_daemon_loop(
        cfg,
        interval_sec=args.prefetch_interval,
        no_cache=args.no_cache,
        include_grades=not args.prefetch_no_grades,
    )


def _export_ics_and_exit(args: argparse.Namespace) -> None:
    """Export ICS without launching TUI."""
    from .api import CanvasAPI
    from .config import ensure_dirs, load_config
    from .ics import export_ics
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

    path = export_ics(items, cfg)
    event_count = sum(1 for it in items if it.due_iso)
    print(f"Exported {event_count} events to {path}")
    sys.exit(0)
