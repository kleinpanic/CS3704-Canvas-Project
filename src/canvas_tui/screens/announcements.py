"""Announcements screens — list and detail views."""

from __future__ import annotations

import contextlib
import os
import threading
import webbrowser
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Footer, RichLog, Static

from ..models import CanvasItem
from ..utils import get_download_dir, sanitize_filename, strip_html

if TYPE_CHECKING:
    from ..app import CanvasTUI


class AnnouncementsScreen(Screen):
    """Announcements list view."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("enter", "ann_open", "Open"),
        ("o", "open_in_browser", "Open in browser"),
        ("w", "download", "Download attachments"),
    ]

    def __init__(self, owner_app: CanvasTUI, announcements: list[CanvasItem]) -> None:
        super().__init__()
        self._owner = owner_app
        self._anns = announcements

    def compose(self) -> ComposeResult:
        with Vertical(id="ann-root"):
            self.table = DataTable(zebra_stripes=True, id="ann-table")
            yield self.table
            yield Footer()

    def on_mount(self) -> None:
        self.table.clear(columns=True)
        self.table.add_columns("Announcement")
        self.table.cursor_type = "row"
        if not self._anns:
            self.table.add_row("[dim]No announcements in current window[/dim]")
        else:
            for it in self._anns:
                self.table.add_row(self._fmt_row(it))
        with contextlib.suppress(Exception):
            self.table.cursor_coordinate = (0, 0)
        self.table.focus()

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.stop()
            self.action_ann_open()
        elif event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    @staticmethod
    def _fmt_row(it: CanvasItem) -> str:
        when = it.due_at or "-"
        rel = f" ({it.due_rel})" if it.due_rel else ""
        code = it.course_code or ""
        title = it.title or "(announcement)"
        return f"{when} — {code} — {title}{rel}"

    def _sel(self) -> CanvasItem | None:
        row = self.table.cursor_row
        if row is None:
            return None
        if 0 <= row < len(self._anns):
            return self._anns[row]
        return None

    def action_ann_open(self) -> None:
        it = self._sel()
        if not it:
            return
        self.app.push_screen(AnnouncementDetailScreen(self._owner, it))

    def action_open_in_browser(self) -> None:
        it = self._sel()
        if not it:
            return
        with contextlib.suppress(Exception):
            webbrowser.open(it.url, new=2)

    def action_download(self) -> None:
        it = self._sel()
        if not it:
            return
        self._owner._async_gather_attachments(it)

    def action_pop(self) -> None:
        self.app.pop_screen()


class AnnouncementDetailScreen(Screen):
    """Full announcement view with body and attachments."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("o", "open_in_browser", "Open in browser"),
        ("w", "download", "Download attachments"),
    ]

    def __init__(self, owner_app: CanvasTUI, item: CanvasItem) -> None:
        super().__init__()
        self._owner = owner_app
        self.item = item
        self.links: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            self.head = Static(id="a-head")
            yield self.head
            self.body = RichLog(highlight=True, wrap=True, id="a-body")
            yield self.body
            self.link_table = DataTable(zebra_stripes=True, id="a-links")
            yield self.link_table
            yield Footer()

    def on_mount(self) -> None:
        it = self.item
        self.head.update(
            f"[b]{it.title}[/b]\n{it.course_code} — {it.course_name}\n"
            f"{it.due_at or '-'} ({it.due_rel or '-'})"
        )
        self.body.write("[dim]Loading announcement…[/dim]")
        self.link_table.clear(columns=True)
        self.link_table.add_columns("Label", "URL")
        threading.Thread(target=self._load, daemon=True).start()

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def _load(self) -> None:
        it = self.item
        api = self._owner.api
        disc = None
        try:
            if it.course_id and it.plannable_id:
                disc = api.fetch_discussion(int(it.course_id), int(it.plannable_id))
        except Exception:
            pass

        def render() -> None:
            self.body.clear()
            text = ""
            if disc:
                text = strip_html(disc.get("message") or "")
                for a in disc.get("attachments") or []:
                    lbl = a.get("display_name") or a.get("filename") or "file"
                    url = a.get("url") or a.get("download_url") or a.get("html_url") or ""
                    if url:
                        self.links.append((lbl, url))
            if not text:
                text = "(No body content.)"
            self.body.write(text)
            self.links = [("Open in browser", it.url), *self.links]
            self.link_table.clear(columns=True)
            self.link_table.add_columns("Label", "URL")
            for lab, url in self.links:
                self.link_table.add_row(lab, url)
            with contextlib.suppress(Exception):
                self.link_table.cursor_coordinate = (0, 0)

        self.app.call_from_thread(render)

    def action_open_in_browser(self) -> None:
        with contextlib.suppress(Exception):
            webbrowser.open(self.item.url, new=2)

    def action_download(self) -> None:
        files = [(lab, url, 0) for (lab, url) in self.links if lab != "Open in browser"]
        if not files:
            return
        dstdir_default = os.path.join(
            get_download_dir(self._owner.api.cfg.download_dir),
            "Canvas",
            sanitize_filename(self.item.course_code),
            sanitize_filename(self.item.title),
        )
        self._owner._show_confirm_path(
            f"{len(files)} attachment(s) detected. Confirm download directory (Enter to accept):",
            dstdir_default,
            "dl_dir",
            {"files": files, "default": dstdir_default, "item": self.item},
        )

    def action_pop(self) -> None:
        self.app.pop_screen()
