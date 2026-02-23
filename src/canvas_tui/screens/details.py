"""Details screen — full assignment/discussion view."""

from __future__ import annotations

import contextlib
import threading
import webbrowser
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Footer, RichLog, Static

from ..models import CanvasItem
from ..utils import strip_html

if TYPE_CHECKING:
    from ..app import CanvasTUI


class DetailsScreen(Screen):
    """Item details view with body text and attachment links."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("o", "open", "Open in browser"),
        ("b", "open", "Open in browser"),
        ("w", "download", "Download"),
        ("enter", "open_link", "Open selected link"),
    ]

    def __init__(self, owner_app: CanvasTUI, item: CanvasItem) -> None:
        super().__init__()
        self._owner = owner_app
        self.item = item
        self.links: list[tuple[str, str]] = []
        self._loaded = False

    def compose(self) -> ComposeResult:
        with Vertical():
            self.head = Static(id="d-head")
            yield self.head
            self.body = RichLog(highlight=True, wrap=True, id="d-body")
            yield self.body
            self.link_table = DataTable(zebra_stripes=True, id="d-links")
            yield self.link_table
            yield Footer()

    def on_mount(self) -> None:
        it = self.item
        self.head.update(f"[b]{it.title}[/b] ({it.course_code} — {it.course_name})")
        self.link_table.clear(columns=True)
        self.link_table.add_columns("Label", "URL")
        self.body.write("[dim]Loading details…[/dim]")
        threading.Thread(target=self._load_details, daemon=True).start()

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def _load_details(self) -> None:
        """Fetch details on background thread."""
        it = self.item
        api = self._owner.api
        ad = sub = disc = None
        try:
            if it.ptype == "assignment" and it.course_id and it.plannable_id:
                ad = api.fetch_assignment_details(int(it.course_id), int(it.plannable_id))
                sub = api.fetch_submission(int(it.course_id), int(it.plannable_id))
            elif it.ptype in ("discussion", "discussion_topic", "announcement") and it.course_id and it.plannable_id:
                disc = api.fetch_discussion(int(it.course_id), int(it.plannable_id))
        except Exception:
            pass
        self.app.call_from_thread(self._render_details, ad, sub, disc)

    def _render_details(
        self,
        ad: dict[str, Any] | None,
        sub: dict[str, Any] | None,
        disc: dict[str, Any] | None,
    ) -> None:
        """Render detail body."""
        self.body.clear()
        self.link_table.clear(columns=True)
        self.link_table.add_columns("Label", "URL")

        it = self.item
        due = it.due_at or "-"
        rel = it.due_rel or "-"
        pts = it.points if it.points is not None else "-"

        score_line = ""
        if sub and sub.get("score") is not None and it.points:
            sc = float(sub["score"])
            pct = (100.0 * sc / float(it.points)) if it.points else 0.0
            score_line = f" • Score: {sc:.2f}/{float(it.points):.2f} ({pct:.0f}%)"

        self.links = [("Open in browser", it.url)]
        lines = [
            f"Type: {it.ptype} • When: {due} ({rel}) • Points: {pts}{score_line}",
            f"Status: {', '.join(it.status_flags) if it.status_flags else '-'}",
            f"URL: {it.url}",
        ]

        if ad:
            desc = strip_html(ad.get("description") or "")
            if desc:
                lines += ["", desc]
            for a in ad.get("attachments", []) or []:
                lbl = a.get("display_name") or a.get("filename") or "file"
                url = a.get("url") or a.get("download_url") or a.get("href") or ""
                if url:
                    self.links.append((lbl, url))

        if disc:
            text = strip_html(disc.get("message") or "")
            if text:
                lines += ["", text]
            for a in disc.get("attachments") or []:
                lbl = a.get("display_name") or a.get("filename") or "file"
                url = a.get("url") or a.get("download_url") or a.get("html_url") or ""
                if url:
                    self.links.append((lbl, url))

        for lab, url in self.links:
            self.link_table.add_row(lab, url)

        self.body.write("\n".join(lines))
        if self.links:
            with contextlib.suppress(Exception):
                self.link_table.cursor_coordinate = (0, 0)
        self._loaded = True

    def _selected_link(self) -> str | None:
        if self.link_table.cursor_row is None or not self.links:
            return None
        return self.links[self.link_table.cursor_row][1]

    def action_open(self) -> None:
        """Open the item URL in browser."""
        with contextlib.suppress(Exception):
            webbrowser.open(self.item.url, new=2)

    def action_open_link(self) -> None:
        """Open the selected link from the link table."""
        url = self._selected_link() or self.item.url
        if not url:
            return
        with contextlib.suppress(Exception):
            webbrowser.open(url, new=2)

    def action_download(self) -> None:
        if not self._loaded:
            return
        self._owner._async_download_from_links(self.item, self.links)

    def action_pop(self) -> None:
        self.app.pop_screen()
