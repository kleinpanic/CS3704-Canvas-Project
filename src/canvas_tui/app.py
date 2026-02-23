"""Main Canvas TUI application."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import DataTable, Footer, Header, Static

from .api import CanvasAPI
from .cache import ResponseCache
from .config import Config, ensure_dirs, load_config
from .filtering import FilterQuery, filter_items, format_filter_summary
from .models import CanvasItem
from .normalize import apply_past_filter, normalize_announcements, normalize_items, serialize_items
from .notifications import DueNotifier
from .screens import (
    AnnouncementsScreen,
    ConfirmPath,
    DetailsScreen,
    FileManagerScreen,
    GradesScreen,
    HelpScreen,
    InputPrompt,
    LoadingScreen,
    SyllabiScreen,
    WeekViewScreen,
)
from .state import StateManager
from .theme import DARK_THEME, LIGHT_THEME, ThemeColors, get_theme
from .utils import absolute_url, get_download_dir, local_dt, sanitize_filename
from .widgets import Pomodoro

# ASCII art Canvas logo (inspired by GideonWolfe/canvas-tui)
CANVAS_LOGO = """[cyan]
  ██████╗ █████╗ ███╗   ██╗██╗   ██╗ █████╗ ███████╗
 ██╔════╝██╔══██╗████╗  ██║██║   ██║██╔══██╗██╔════╝
 ██║     ███████║██╔██╗ ██║██║   ██║███████║███████╗
 ██║     ██╔══██║██║╚██╗██║╚██╗ ██╔╝██╔══██║╚════██║
 ╚██████╗██║  ██║██║ ╚████║ ╚████╔╝ ██║  ██║███████║
  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝  ╚═══╝  ╚═╝  ╚═╝╚══════╝
[/cyan]"""


_TYPE_ICONS: dict[str, str] = {
    "assignment": "📝 assign",
    "quiz": "📋 quiz",
    "discussion": "💬 discuss",
    "discussion_topic": "💬 discuss",
    "announcement": "📢 announce",
    "calendar_event": "📅 event",
    "planner_note": "📌 note",
    "wiki_page": "📄 page",
}


class CanvasTUI(App):
    """Main Canvas TUI application."""

    CSS = """
    /* === Main layout === */
    Screen { layout: vertical; }
    #main-split { layout: horizontal; height: 1fr; }
    #left-panel {
        width: 1fr;
        min-width: 40;
        max-width: 64;
        border-right: solid #30363d;
    }
    #right-panel { width: 3fr; }

    /* === Left panel sections === */
    #info {
        padding: 1 2;
        height: auto;
        max-height: 16;
    }
    #details {
        padding: 1 2;
        border-top: solid #30363d;
        height: 1fr;
        min-height: 8;
        overflow-y: auto;
    }
    #pomodoro {
        padding: 0 2;
        border-top: solid #30363d;
        height: 3;
    }
    #progress-bar {
        padding: 0 2;
        border-top: solid #30363d;
        height: 3;
    }

    /* === Right panel === */
    #main-table {
        height: 1fr;
        border: none;
    }

    /* === Status bar (bottom dock) === */
    #status-bar {
        dock: bottom;
        height: 1;
        background: #161b22;
        color: #8b949e;
        padding: 0 1;
    }

    /* === Syllabi split === */
    #syl-root { height: 1fr; width: 1fr; }
    #syl-split { layout: horizontal; height: 1fr; }
    #syl-list { width: 1fr; min-width: 28; max-width: 56; border-right: solid #30363d; }
    #syl-preview { height: 1fr; width: 3fr; overflow: auto; padding: 1 2; }

    /* === Announcements === */
    #ann-root { height: 1fr; width: 1fr; }
    #ann-table { width: 1fr; height: 1fr; }

    /* === Grades === */
    #grades-root { height: 1fr; width: 1fr; }
    #grades-split { layout: horizontal; height: 1fr; }
    #grades-courses { width: 1fr; min-width: 24; max-width: 40; border-right: solid #30363d; }
    #grades-detail { width: 3fr; }
    #grades-summary { padding: 1 2; height: auto; max-height: 8; border-bottom: solid #30363d; }
    #grades-table { height: 1fr; }

    /* === Files === */
    #files-root { height: 1fr; width: 1fr; }
    #files-breadcrumb { height: 1; padding: 0 1; background: #161b22; }
    #files-split { layout: horizontal; height: 1fr; }
    #files-courses { width: 1fr; min-width: 20; max-width: 36; border-right: solid #30363d; }
    #files-content { width: 3fr; }
    #files-table { height: 1fr; }
    #files-status { height: 1; padding: 0 1; background: #161b22; }

    /* === Week view === */
    #week-root { height: 1fr; width: 1fr; }
    #week-label { height: 2; padding: 0 2; }
    #week-grid {
        grid-size: 7 1;
        grid-gutter: 0 1;
        height: 1fr;
        padding: 0 1;
    }
    .day-cell {
        height: 1fr;
        border: solid #30363d;
        padding: 0 1;
        overflow-y: auto;
    }

    /* === Detail screens === */
    #d-head, #a-head { padding: 1 2; height: auto; border-bottom: solid #30363d; }
    #d-body, #a-body { height: 1fr; overflow: auto; padding: 1 2; }
    #d-links, #a-links { height: 10; border-top: solid #30363d; }

    /* === Help screen === */
    #help-scroll { padding: 2 4; }
    #help-text { width: 1fr; }

    /* === Modals === */
    InputPrompt, ConfirmPath {
        align: center middle;
    }
    #prompt-title { padding: 1 2; text-style: bold; }
    #prompt-input { margin: 0 2; }
    #prompt-buttons { padding: 1 2; }

    /* === Loading === */
    LoadingScreen {
        align: center middle;
    }

    /* === DataTable global === */
    DataTable { scrollbar-size: 1 1; }
    DataTable > .datatable--cursor { background: #30363d; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("o", "open", "Open in browser"),
        ("enter", "open_details", "Open details"),
        ("d", "quick_preview", "Quick details"),
        ("y", "yank_url", "Copy URL"),
        ("w", "download", "Download attachments"),
        ("c", "export_ics", "Export ICS"),
        ("C", "export_ics_and_import", "Export+calcurse -i"),
        ("g", "open_course", "Open course"),
        ("/", "filter", "Filter"),
        ("x", "toggle_hide", "Hide/Unhide"),
        ("H", "toggle_show_hidden", "Show hidden"),
        ("1", "pomo30", "Pomodoro 30m"),
        ("2", "pomo60", "Pomodoro 1h"),
        ("3", "pomo120", "Pomodoro 2h"),
        ("P", "pomo_custom", "Pomodoro custom"),
        ("0", "pomo_stop", "Pomodoro stop"),
        ("S", "open_syllabi", "Syllabi"),
        ("A", "open_announcements", "Announcements"),
        ("G", "open_grades", "Grades"),
        ("F", "open_files", "Files"),
        ("W", "open_week", "Week view"),
        ("T", "toggle_theme", "Theme"),
        ("question_mark", "show_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cfg: Config = load_config()
        ensure_dirs(self.cfg)
        cache_dir = os.path.join(self.cfg.export_dir, "cache")
        self._response_cache = ResponseCache(cache_dir, default_ttl=900)
        self.api: CanvasAPI = CanvasAPI(self.cfg, response_cache=self._response_cache)
        self.state: StateManager = StateManager(self.cfg.state_path)

        self.items: list[CanvasItem] = []
        self.announcements: list[CanvasItem] = []
        self.course_cache: dict[int, tuple[str, str]] = {}
        self.filtered: list[int] | None = None
        self.show_hidden = False
        self.table: DataTable | None = None
        self.info: Static | None = None
        self.details: Static | None = None
        self.pomo: Pomodoro | None = None
        self.status_bar: Static | None = None
        self._refresh_lock = threading.Lock()
        self._last_refresh = 0.0
        self._bg_refresh_thread: threading.Thread | None = None
        self._stop_bg = False
        self._submission_cache: dict[tuple[int, int], dict[str, Any]] = {}
        self._pending: dict[str, tuple[str, dict[str, Any]]] = {}
        self._error_count = 0
        self._theme: ThemeColors = get_theme("dark")
        self._notifier = DueNotifier(
            tz=self.cfg.user_tz,
            get_items=lambda: list(self.items),
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-split"):
            with Vertical(id="left-panel"):
                self.info = Static(id="info")
                yield self.info
                self.details = Static(id="details")
                yield self.details
                self.pomo = Pomodoro(on_state_change=self._persist_pomo)
                yield self.pomo
                self.progress = Static(id="progress-bar")
                yield self.progress
            with Vertical(id="right-panel"):
                self.table = DataTable(zebra_stripes=True, id="main-table")
                yield self.table
        self.status_bar = Static(id="status-bar")
        yield self.status_bar
        yield Footer()

    def _persist_pomo(self, end_ts: float | None) -> None:
        self.state.set_pomo_end(end_ts)

    def _update_status_bar(self, extra: str = "") -> None:
        """Update the bottom status bar."""
        if not self.status_bar:
            return
        rate = self.api.rate_limit_remaining
        rate_str = f"Rate: {rate}" if rate is not None else "Rate: ?"
        refresh_str = (
            f"Last refresh: {dt.datetime.fromtimestamp(self._last_refresh).strftime('%H:%M:%S')}"
            if self._last_refresh > 0
            else "Last refresh: never"
        )
        err_str = f"Errors: {self._error_count}" if self._error_count else ""
        offline_str = "[yellow]⚡ OFFLINE[/yellow]" if self.api.is_offline else ""
        cache_stats = self._response_cache.stats()
        cache_str = f"Cache: {cache_stats['entries']} ({cache_stats['size_kb']}KB)"
        parts = [p for p in [offline_str, refresh_str, rate_str, cache_str, err_str, extra] if p]
        self.status_bar.update(" │ ".join(parts))

    # ---------- mount / teardown ----------
    def on_mount(self) -> None:
        self._setup_table()
        # Load cached data immediately for instant display
        try:
            cached = self.state.get_cached_items()
            if cached:
                self.items = [CanvasItem.from_dict(d) for d in cached]
                self._render_info()
                self._render_table()
        except Exception:
            pass

        self.push_screen(LoadingScreen())
        self.call_later(self._initial_load)

        # Resume pomodoro
        try:
            end_ts = self.state.get_pomo_end()
            if end_ts is not None and end_ts > time.time():
                self.pomo.resume_until(end_ts)
        except Exception:
            pass

        # Background auto-refresh
        if self.cfg.auto_refresh_sec > 0:
            self._bg_refresh_thread = threading.Thread(target=self._bg_refresh_loop, daemon=True)
            self._bg_refresh_thread.start()

        self._update_status_bar()
        self._notifier.start()

    def _initial_load(self) -> None:
        try:
            self.refresh_data()
        finally:
            with contextlib.suppress(Exception):
                self.pop_screen()

    def on_unmount(self) -> None:
        self._stop_bg = True
        self._notifier.stop()

    # ---------- table ----------
    def _setup_table(self) -> None:
        assert self.table is not None
        self.table.clear(columns=True)
        self.table.add_columns("Due", "Rel", "Type", "Course", "Title", "Pts", "Status")
        self.table.cursor_type = "row"
        self.table.zebra_stripes = True

    def on_data_table_row_selected(self, msg: DataTable.RowSelected) -> None:
        src = getattr(msg, "data_table", None) or getattr(msg, "control", None)
        if src is not self.table:
            return
        self.action_open_details()

    def on_key(self, event: Key) -> None:
        if event.key in ("1", "2", "3", "0", "P"):
            event.stop()
            if event.key == "1":
                self.action_pomo30()
            elif event.key == "2":
                self.action_pomo60()
            elif event.key == "3":
                self.action_pomo120()
            elif event.key == "0":
                self.action_pomo_stop()
            elif event.key == "P":
                self.action_pomo_custom()

    def _stats(self) -> tuple[int, int, int, int]:
        """Compute stats in a single pass over items."""
        now = dt.datetime.now(ZoneInfo(self.cfg.user_tz))
        today = now.strftime("%m/%d/%Y")
        total = len(self.items)
        due_today = overdue = submitted = 0
        for it in self.items:
            is_submitted = "submitted" in it.status_flags
            if is_submitted:
                submitted += 1
            if it.due_at.startswith(today):
                due_today += 1
            if not is_submitted and it.due_rel.endswith("ago"):
                overdue += 1
        return total, due_today, overdue, submitted

    def _render_info(self) -> None:
        now = dt.datetime.now(ZoneInfo(self.cfg.user_tz))
        total, due_today, overdue, submitted = self._stats()
        prog = f"{submitted}/{total}" if total else "0/0"
        s = (
            f"{CANVAS_LOGO}\n"
            f"[b]Canvas TODO (next {self.cfg.days_ahead}d; past {self.cfg.past_hours}h if unsubmitted)[/b]\n"
            f"{self.cfg.base_url}\n"
            f"[dim]{now.strftime('%m/%d/%Y %H:%M %Z')}[/dim]\n"
            f"Items: {total} • Today: {due_today} • Overdue: {overdue} • "
            f"Submitted: {submitted} (progress {prog})\n"
            f"[dim]Press ? for help[/dim]"
        )
        self.info.update(s)

    def _visible_items(self) -> list[CanvasItem]:
        base = self.items
        if not self.show_hidden:
            base = [it for it in base if self.state.get_visibility(it.key) != 2]
        if self.filtered is None:
            return base
        return [base[i] for i in range(len(base)) if i in self.filtered]

    def _color_for_item(self, it: CanvasItem) -> str:
        t = self._theme
        if "submitted" in it.status_flags:
            return t.success
        if not it.due_iso:
            return t.normal
        now = dt.datetime.now(ZoneInfo(self.cfg.user_tz))
        due = local_dt(it.due_iso, self.cfg.user_tz)
        delta_h = (due - now).total_seconds() / 3600.0
        if delta_h < 0:
            return t.overdue
        if delta_h <= 8:
            return t.urgent
        if delta_h <= 12:
            return t.soon
        if delta_h <= 24:
            return t.today
        if delta_h <= 48:
            return t.upcoming
        return t.normal

    def _prefetch_submissions(self) -> None:
        """Prefetch submissions for graded items during refresh (background-safe)."""
        for it in self.items:
            if "graded" in it.status_flags and it.course_id and it.plannable_id and it.points:
                key = (int(it.course_id), int(it.plannable_id))
                if key not in self._submission_cache:
                    with contextlib.suppress(Exception):
                        sub = self.api.fetch_submission(*key)
                        if sub:
                            self._submission_cache[key] = sub

    def _pts_cell(self, it: CanvasItem) -> str:
        pts = it.points
        if "graded" in it.status_flags and it.course_id and it.plannable_id and pts:
            key = (int(it.course_id), int(it.plannable_id))
            sub = self._submission_cache.get(key)
            if sub and sub.get("score") is not None:
                sc = float(sub["score"])
                pct = (100.0 * sc / float(pts)) if pts else 0.0
                return f"{sc:.0f}/{float(pts):.0f} ({pct:.0f}%)"
        return f"{pts:.0f}" if isinstance(pts, (int, float)) else "-"

    def _render_table(self) -> None:
        assert self.table is not None
        self.table.clear()
        visible = self._visible_items()
        if not visible:
            self.table.add_row("-", "-", "-", "-", "[dim]No items matching filters[/dim]", "-", "-")
            return
        for it in visible:
            ptype_display = _TYPE_ICONS.get(it.ptype, it.ptype)
            tcell = f"[{self._color_for_item(it)}]{ptype_display}[/]"
            vis = self.state.get_visibility(it.key)
            title = it.title if vis == 0 else f"[dim]{it.title}[/]"
            row = [
                it.due_at or "-",
                it.due_rel or "-",
                tcell,
                it.course_code,
                title,
                self._pts_cell(it),
                ", ".join(it.status_flags) if it.status_flags else "-",
            ]
            self.table.add_row(*row)
        self.table.focus()
        with contextlib.suppress(Exception):
            self.table.cursor_coordinate = (0, 0)

    def _render_progress(self) -> None:
        total, _, _, submitted = self._stats()
        if not total:
            self.progress.update("[dim]Progress: 0/0[/dim]")
            return
        pct = submitted / total
        slices = ["○", "◔", "◑", "◕", "●"]
        i = min(int(pct * (len(slices) - 1) + 0.5), len(slices) - 1)
        bar_len = 20
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)
        self.progress.update(f"Progress: {submitted}/{total}  {slices[i]} {int(pct * 100)}%\n[{bar}]")

    # ---------- refresh ----------
    def _bg_refresh_loop(self) -> None:
        while not self._stop_bg:
            time.sleep(self.cfg.auto_refresh_sec)
            if self._stop_bg:
                break
            with contextlib.suppress(Exception):
                self.refresh_data(silent=True)

    def action_refresh(self) -> None:
        now = time.time()
        if (now - self._last_refresh) < self.cfg.refresh_cooldown:
            self.details.update(
                f"[yellow]Refresh ignored:[/yellow] cooldown {self.cfg.refresh_cooldown:.1f}s"
            )
            return
        if self._refresh_lock.locked():
            self.details.update("[yellow]Refresh already in progress…[/yellow]")
            return
        self.refresh_data()

    def refresh_data(self, silent: bool = False) -> None:
        if not self._refresh_lock.acquire(blocking=False):
            return
        if not silent:
            self.details.update("[dim]Refreshing…[/dim]")

        def worker() -> None:
            try:
                course_cache = self.api.fetch_current_courses()
                raw = self.api.fetch_planner_items()
                all_items = normalize_items(raw, self.api, self.cfg.user_tz)
                items = apply_past_filter(all_items, self.cfg.past_hours, self.cfg.user_tz)

                ann_raw: list[dict[str, Any]] = []
                try:
                    ann_raw = self.api.fetch_announcements(list(course_cache.keys()))
                except Exception:
                    ann_raw = []
                announcements = normalize_announcements(
                    ann_raw, course_cache, self.cfg.base_url, self.cfg.user_tz
                )

                # Migrate legacy keys
                key_map = {it.legacy_key: it.key for it in items if it.legacy_key}
                self.state.migrate_visibility_keys(key_map)

                # Prefetch submissions for graded items (in background thread)
                self.items = items  # Temporarily set for prefetch
                self._prefetch_submissions()

                def apply_ui() -> None:
                    self.course_cache = course_cache
                    self.items = items
                    self.announcements = announcements
                    self.filtered = None
                    self._submission_cache.clear()
                    self.state.update_cache(
                        serialize_items(items), serialize_items(announcements)
                    )
                    self._render_info()
                    self._render_table()
                    if not silent:
                        self.details.update(
                            "[dim]Select an item and press Enter (full) or d (quick). "
                            "Use A for announcements, S for syllabi.[/dim]"
                        )
                    self._last_refresh = time.time()
                    self._render_progress()
                    self._update_status_bar()

                self.call_from_thread(apply_ui)
            except Exception as exc:
                self._error_count += 1
                err_msg = str(exc)
                self.call_from_thread(lambda: self.details.update(f"[red]Error:[/red] {err_msg}"))
                self.call_from_thread(lambda: self._update_status_bar())
            finally:
                self._refresh_lock.release()

        threading.Thread(target=worker, daemon=True).start()

    def _selected_idx(self) -> int | None:
        vis = self._visible_items()
        if not vis or not self.table:
            return None
        if self.table.cursor_row is None:
            return None
        return self.table.cursor_row

    def _selected_item(self) -> CanvasItem | None:
        vis = self._visible_items()
        idx = self._selected_idx()
        if idx is None or idx >= len(vis):
            return None
        return vis[idx]

    # ---------- Prompt plumbing (using UUIDs) ----------
    def _show_input(self, title: str, placeholder: str, default: str, kind: str, ctx: dict[str, Any]) -> None:
        scr = InputPrompt(title, placeholder, default)
        modal_id = uuid.uuid4().hex
        self._pending[modal_id] = (kind, ctx)
        scr._modal_id = modal_id  # type: ignore[attr-defined]
        self.push_screen(scr)

    def _show_confirm_path(self, msg: str, default_path: str, kind: str, ctx: dict[str, Any]) -> None:
        scr = ConfirmPath(msg, default_path)
        modal_id = uuid.uuid4().hex
        self._pending[modal_id] = (kind, ctx)
        scr._modal_id = modal_id  # type: ignore[attr-defined]
        self.push_screen(scr)

    def on_screen_dismissed(self, event: Any) -> None:
        modal_id = getattr(event.screen, "_modal_id", None)
        if modal_id is None:
            return
        entry = self._pending.pop(modal_id, None)
        if not entry:
            return
        kind, ctx = entry
        res = event.result

        if kind == "filter":
            raw = (res or "").strip()
            if not raw:
                self.details.update("[dim]Filter cancelled[/dim]")
                return
            query = FilterQuery.parse(raw)
            if query.is_empty:
                self.filtered = None
                self._render_table()
                self.details.update("[dim]Filter cleared[/dim]")
                return
            # Filter against base items (before visibility filter for indices)
            base = self.items if self.show_hidden else [it for it in self.items if self.state.get_visibility(it.key) != 2]
            idxs = filter_items(base, query)
            self.filtered = idxs if idxs else None
            # Persist last filter
            self.state.set("last_filters", {"raw": raw})
            self._render_table()
            self.details.update(format_filter_summary(query, len(idxs), len(base)))
        elif kind == "pomo":
            try:
                mins = int(res)
                self.pomo.start(mins)
            except Exception:
                self.details.update("[yellow]Invalid minutes[/yellow]")
        elif kind == "dl_dir":
            ok, path = res if isinstance(res, tuple) else (False, "")
            if not ok:
                self.details.update("[dim]Download cancelled[/dim]")
                return
            files = ctx["files"]
            dstdir = path or ctx["default"]
            os.makedirs(dstdir, exist_ok=True)
            if not files:
                self.details.update("[yellow]No attachments detected[/yellow]")
                return
            if len(files) >= 6:
                total_known = sum(sz for _, _, sz in files)
                human = f"{total_known / 1_000_000:.1f} MB" if total_known else "unknown size"
                self._show_input(
                    f"Download {len(files)} files (~{human})? Type YES to proceed:",
                    "",
                    "",
                    "dl_many",
                    {"files": files, "dir": dstdir},
                )
            else:
                self._async_do_download(files, dstdir)
        elif kind == "dl_many":
            if (res or "").upper() != "YES":
                self.details.update("[dim]Download cancelled[/dim]")
                return
            self._async_do_download(ctx["files"], ctx["dir"])

    # ---------- async helpers ----------
    def _async_download_from_links(self, item: CanvasItem, links: list[tuple[str, str]]) -> None:
        files = [(lab, url, 0) for (lab, url) in links if lab != "Open in browser"]
        dstdir_default = os.path.join(
            get_download_dir(self.cfg.download_dir),
            "Canvas",
            sanitize_filename(item.course_code),
            sanitize_filename(item.title),
        )
        msg = f"{len(files)} attachment(s) detected. Confirm download directory (Enter to accept):"
        self._show_confirm_path(msg, dstdir_default, "dl_dir", {"files": files, "default": dstdir_default, "item": item})

    def _async_gather_attachments(self, it: CanvasItem) -> None:
        self.details.update("[dim]Scanning attachments…[/dim]")

        def worker() -> None:
            files: list[tuple[str, str, int]] = []
            try:
                if it.ptype == "assignment" and it.course_id and it.plannable_id:
                    ad = self.api.fetch_assignment_details(int(it.course_id), int(it.plannable_id))
                    for a in ad.get("attachments", []) or []:
                        name = a.get("display_name") or a.get("filename") or "file"
                        url = a.get("url") or a.get("download_url") or a.get("href")
                        size = int(a.get("size") or 0)
                        if url:
                            files.append((name, url, size))
            except Exception:
                pass
            if not files:
                try:
                    r = self.api.session.get(it.url, timeout=self.cfg.http_timeout)
                    if r.ok:
                        for m in re.finditer(r'href="([^"]+)"', r.text):
                            href = m.group(1)
                            if "/files/" in href and "download" in href:
                                files.append(
                                    (
                                        os.path.basename(urlparse(href).path) or "file",
                                        absolute_url(href, self.cfg.base_url),
                                        0,
                                    )
                                )
                except Exception:
                    pass
            dstdir_default = os.path.join(
                get_download_dir(self.cfg.download_dir),
                "Canvas",
                sanitize_filename(it.course_code),
                sanitize_filename(it.title),
            )
            self.app.call_from_thread(
                self._show_confirm_path,
                f"{len(files)} attachment(s) detected. Confirm download directory (Enter to accept):",
                dstdir_default,
                "dl_dir",
                {"files": files, "default": dstdir_default, "item": it},
            )

        threading.Thread(target=worker, daemon=True).start()

    def _async_do_download(self, files: list[tuple[str, str, int]], dstdir: str) -> None:
        self.details.update("[dim]Downloading…[/dim]")

        def worker() -> None:
            okc, fail, total = 0, 0, 0
            for name, url, _size in files:
                fname = os.path.join(dstdir, sanitize_filename(name))
                try:
                    with self.api.session.get(url, stream=True, timeout=self.cfg.http_timeout) as resp:
                        resp.raise_for_status()
                        with open(fname, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                                    total += len(chunk)
                    okc += 1
                    if self.cfg.open_after_dl and shutil.which("xdg-open"):
                        subprocess.Popen(["xdg-open", fname])
                except Exception:
                    fail += 1
            self.app.call_from_thread(
                self.details.update,
                f"[green]Downloaded {okc}[/green], [red]{fail} failed[/red] → {dstdir}  "
                f"(total {total / 1_000_000:.2f} MB)",
            )

        threading.Thread(target=worker, daemon=True).start()

    # ---------- actions ----------
    def action_open(self) -> None:
        it = self._selected_item()
        if not it:
            return
        with contextlib.suppress(Exception):
            webbrowser.open(it.url, new=2)

    def action_quick_preview(self) -> None:
        it = self._selected_item()
        if not it:
            return
        pts = "-" if it.points is None else f"{it.points:.0f}"
        s = (
            f"[b]{it.title}[/b]\n"
            f"{it.course_code} — {it.course_name}\n"
            f"Type: {it.ptype} • Due: {it.due_at or '-'} ({it.due_rel or '-'}) • Points: {pts}\n"
            f"Status: {', '.join(it.status_flags) if it.status_flags else '-'}\n"
            f"URL: {it.url}"
        )
        self.details.update(s)

    def action_open_details(self) -> None:
        it = self._selected_item()
        if not it:
            return
        self.push_screen(DetailsScreen(self, it))

    def action_yank_url(self) -> None:
        it = self._selected_item()
        if not it:
            return
        url = it.url
        copied = False
        for cmd in (("xclip", "-selection", "clipboard"), ("wl-copy",)):
            if shutil.which(cmd[0]):
                try:
                    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    p.communicate(url.encode("utf-8"), timeout=2)
                    if p.returncode == 0:
                        copied = True
                        break
                except Exception:
                    pass
        self.details.update("[green]Copied URL[/green]" if copied else f"[yellow]Copy failed[/yellow]: {url}")

    def action_download(self) -> None:
        it = self._selected_item()
        if not it:
            return
        self._async_gather_attachments(it)

    def _export_all_ics(self) -> str:
        from .ics import export_ics
        return export_ics(self.items, self.cfg)

    def action_export_ics(self) -> None:
        try:
            path = self._export_all_ics()
            self.details.update(f"[green]ICS exported[/green]: {path}")
        except Exception as e:
            self.details.update(f"[red]ICS export failed:[/red] {e}")

    def action_export_ics_and_import(self) -> None:
        try:
            path = self._export_all_ics()
            if shutil.which("calcurse"):
                p = subprocess.run(["calcurse", "-i", path], capture_output=True, text=True)
                if p.returncode == 0:
                    self.details.update(f"[green]ICS imported to calcurse[/green]: {path}")
                else:
                    self.details.update(
                        f"[yellow]calcurse import error[/yellow]: {p.stderr.strip() or p.stdout.strip()}"
                    )
            else:
                self.details.update(f"[yellow]calcurse not found[/yellow]. ICS at {path}")
        except Exception as e:
            self.details.update(f"[red]ICS export/import failed:[/red] {e}")

    def action_open_course(self) -> None:
        it = self._selected_item()
        if not it:
            return
        m = re.search(r"/courses/(\d+)", it.url)
        if m:
            url = f"{self.cfg.base_url}/courses/{m.group(1)}"
            with contextlib.suppress(Exception):
                webbrowser.open(url, new=2)
        else:
            self.details.update("[yellow]No course link found[/yellow]")

    def action_filter(self) -> None:
        if self.filtered is not None:
            self.filtered = None
            self._render_table()
            self.details.update("[dim]Filter cleared[/dim]")
            return
        last = self.state.get("last_filters", {})
        last_raw = last.get("raw", "") if isinstance(last, dict) else ""
        self._show_input(
            "Filter (e.g. course:CS3214 type:assignment status:graded):",
            "type:assignment",
            last_raw,
            "filter",
            {},
        )

    def action_toggle_hide(self) -> None:
        it = self._selected_item()
        if not it:
            return
        self.state.cycle_visibility(it.key)
        self._render_table()

    def action_toggle_show_hidden(self) -> None:
        self.show_hidden = not self.show_hidden
        self._render_table()
        self.details.update(
            "[dim]Showing hidden[/dim]" if self.show_hidden else "[dim]Hidden suppressed[/dim]"
        )

    def action_show_help(self) -> None:
        """Show full help screen overlay."""
        self.push_screen(HelpScreen())

    def action_open_grades(self) -> None:
        """Open grades overview screen."""
        if not self.course_cache:
            self.details.update("[yellow]No courses cached yet — refresh first[/yellow]")
            return
        self.push_screen(GradesScreen(self, self.course_cache))

    def action_toggle_theme(self) -> None:
        """Toggle between dark and light themes."""
        if self._theme.name == "dark":
            self._theme = LIGHT_THEME
            self.dark = False
        else:
            self._theme = DARK_THEME
            self.dark = True
        self._render_info()
        self._update_status_bar(f"Theme: {self._theme.name}")

    # Pomodoro
    def action_pomo30(self) -> None:
        self.pomo.start(30)

    def action_pomo60(self) -> None:
        self.pomo.start(60)

    def action_pomo120(self) -> None:
        self.pomo.start(120)

    def action_pomo_custom(self) -> None:
        self._show_input("Minutes:", "", "45", "pomo", {})

    def action_pomo_stop(self) -> None:
        self.pomo.stop()

    # Views
    def action_open_syllabi(self) -> None:
        if not self.course_cache:
            self.details.update("[yellow]No courses cached yet[/yellow]")
            return
        self.push_screen(SyllabiScreen(self, self.course_cache))

    def action_open_announcements(self) -> None:
        if not self.announcements:
            self.details.update("[dim]No announcements in window[/dim]")
            return
        self.push_screen(AnnouncementsScreen(self, self.announcements))

    def action_open_files(self) -> None:
        """Open file manager screen."""
        if not self.course_cache:
            self.details.update("[yellow]No courses cached yet — refresh first[/yellow]")
            return
        self.push_screen(FileManagerScreen(self, self.course_cache))

    def action_open_week(self) -> None:
        """Open calendar week view."""
        self.push_screen(WeekViewScreen(self, self.items))


def main() -> None:
    """Entry point for the Canvas TUI application."""
    from .cli import handle_non_tui_commands, parse_args

    args = parse_args()

    # Handle non-TUI commands first
    if handle_non_tui_commands(args):
        return

    app = CanvasTUI()

    # Apply CLI overrides
    if args.no_cache:
        app.api._no_cache = True
    if args.days_ahead is not None:
        app.cfg.days_ahead = args.days_ahead
    if args.past_hours is not None:
        app.cfg.past_hours = args.past_hours
    if args.theme == "light":
        app._theme = LIGHT_THEME
        app.dark = False

    app.run()


if __name__ == "__main__":
    main()
