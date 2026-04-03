"""Syllabi screen — course list with preview panel."""

from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import subprocess
import tempfile
import threading
import webbrowser
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Footer, RichLog

from ..utils import get_download_dir, sanitize_filename, strip_html

if TYPE_CHECKING:
    from ..app import CanvasTUI

# Track temp files for cleanup at exit
_temp_files: list[str] = []


def _cleanup_temp_files() -> None:
    """Clean up any temp files created during syllabus preview."""
    for path in _temp_files:
        with contextlib.suppress(Exception):
            os.remove(path)


atexit.register(_cleanup_temp_files)


class SyllabiScreen(Screen):
    """Course syllabi list with right-side preview panel."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("enter", "syl_open", "Preview/View"),
        ("w", "save", "Save"),
        ("b", "browser", "Open in browser"),
        ("v", "view_native", "Open native viewer"),
    ]

    def __init__(self, owner_app: CanvasTUI, courses: dict[int, tuple[str, str]]) -> None:
        super().__init__()
        self._owner = owner_app
        self.courses = courses
        self.curr_id: int | None = None
        self.curr_html: str | None = None
        self.curr_file: dict[str, Any] | None = None
        self.curr_preview_text: str | None = None
        self.curr_browser_url: str | None = None
        self._row_to_cid: list[int] = []
        self.body: RichLog | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="syl-root"):
            with Horizontal(id="syl-split"):
                self.table = DataTable(zebra_stripes=True, id="syl-list")
                yield self.table
                self.preview = Vertical(id="syl-preview")
                yield self.preview
            yield Footer()

    def on_mount(self) -> None:
        self.table.clear(columns=True)
        self.table.add_columns("Course")
        self.table.cursor_type = "row"
        self._row_to_cid.clear()
        for cid, (code, name) in sorted(self.courses.items(), key=lambda kv: (kv[1][0], kv[0])):
            self.table.add_row(f"{code or cid} — {name or ''}")
            self._row_to_cid.append(cid)
        with contextlib.suppress(Exception):
            self.table.cursor_coordinate = (0, 0)
        cid = self._selected_course()
        if cid is not None:
            self._open_async(int(cid))

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            self.app.pop_screen()

    def _container(self) -> Vertical:
        return self.query_one("#syl-preview", Vertical)

    def _reset_preview(self) -> None:
        cont = self._container()
        try:
            for child in list(cont.children):
                child.remove()
        except Exception:
            pass
        self.body = RichLog(highlight=True, wrap=True)
        cont.mount(self.body)

    def _selected_course(self) -> int | None:
        row = self.table.cursor_row
        if row is None:
            return None
        if 0 <= row < len(self._row_to_cid):
            return self._row_to_cid[row]
        return None

    def _render_text(self, text: str) -> None:
        self._reset_preview()
        assert self.body is not None
        self.body.write(text)

    @staticmethod
    def _pdftotext_available() -> bool:
        return shutil.which("pdftotext") is not None

    def _preview_pdf_from_url(self, url: str) -> None:
        """Download and convert PDF for preview."""
        api = self._owner.api

        def worker() -> None:
            try:
                with api.session.get(url, timeout=api.cfg.http_timeout) as r:
                    r.raise_for_status()
                    data = r.content
                if not self._pdftotext_available():
                    msg = "(pdftotext not found; press 'b' to open in browser or 'w' to save.)"
                else:
                    with tempfile.NamedTemporaryFile(prefix="canvas_syl_", suffix=".pdf", delete=False) as f:
                        f.write(data)
                        pdf_path = f.name
                    _temp_files.append(pdf_path)
                    txt_path = pdf_path + ".txt"
                    _temp_files.append(txt_path)
                    try:
                        subprocess.run(
                            ["pdftotext", "-layout", pdf_path, txt_path],
                            check=False,
                            timeout=10,
                        )
                        if os.path.exists(txt_path):
                            with open(txt_path, encoding="utf-8", errors="ignore") as tf:
                                msg = tf.read().strip() or "(empty text after conversion)"
                        else:
                            msg = "(conversion failed)"
                    finally:
                        # Clean up immediately when possible
                        for p in (pdf_path, txt_path):
                            try:
                                os.remove(p)
                                _temp_files.remove(p)
                            except Exception:
                                pass
                self.app.call_from_thread(self._render_text, msg)
            except Exception as e:
                self.app.call_from_thread(self._render_text, f"(preview failed: {e})")

        threading.Thread(target=worker, daemon=True).start()

    def _open_async(self, cid: int) -> None:
        """Load syllabus asynchronously."""
        self._render_text("[dim]Loading syllabus…[/dim]")
        api = self._owner.api

        def worker() -> None:
            html = ""
            try:
                html = api.fetch_course_syllabus(int(cid)) or ""
            except Exception:
                html = ""

            if html and html.strip():
                text = strip_html(html)
                self.curr_id = cid
                self.curr_html = html
                self.curr_file = None
                self.curr_preview_text = text
                self.curr_browser_url = None
                self.app.call_from_thread(self._render_text, text or "(syllabus HTML empty)")
                return

            files: list[dict[str, Any]] = []
            try:
                cand: dict[int, dict[str, Any]] = {}
                for term in ("syllab", "syllabus", "outline"):
                    for f in api.search_course_files(int(cid), term):
                        fid = f.get("id")
                        if fid is not None:
                            cand[fid] = f
                files = list(cand.values())

                def is_pdf(f: dict[str, Any]) -> bool:
                    ct = str(f.get("content-type", "")).lower()
                    name = (f.get("display_name") or f.get("filename") or "").lower()
                    return ct.endswith("pdf") or name.endswith(".pdf")

                def name_lc(f: dict[str, Any]) -> str:
                    return (f.get("display_name") or f.get("filename") or "").lower()

                files.sort(key=lambda f: (not is_pdf(f), "syllab" not in name_lc(f), -(f.get("size") or 0)))
            except Exception:
                files = []

            if not files:
                self.app.call_from_thread(self._render_text, "(No syllabus HTML and no matching files.)")
                return

            f0 = files[0]
            name = f0.get("display_name") or f0.get("filename") or "syllabus.pdf"
            url = f0.get("download_url") or f0.get("url") or f0.get("html_url")
            text = (
                f"Found file: {name} ({(f0.get('size') or 0) / 1_000_000:.2f} MB)\n"
                "Press Enter to preview (PDF→text) or 'b' to open in browser; 'w' to save."
            )
            self.curr_id = cid
            self.curr_file = f0
            self.curr_html = None
            self.curr_preview_text = None
            self.curr_browser_url = url
            self.app.call_from_thread(self._render_text, text)

        threading.Thread(target=worker, daemon=True).start()

    def action_syl_open(self) -> None:
        cid = self._selected_course()
        if cid is not None and cid != self.curr_id:
            self._open_async(int(cid))
            return
        if self.curr_browser_url:
            self._render_text("[dim]Downloading + converting PDF…[/dim]")
            self._preview_pdf_from_url(self.curr_browser_url)

    def action_save(self) -> None:
        """Save syllabus file."""
        api = self._owner.api
        if self.curr_html and self.curr_id:
            code, _ = self.courses.get(self.curr_id, ("", "Course"))
            dstdir = os.path.join(
                get_download_dir(api.cfg.download_dir),
                "Canvas",
                sanitize_filename(code or str(self.curr_id)),
            )
            os.makedirs(dstdir, exist_ok=True)
            path = os.path.join(dstdir, "Syllabus.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.curr_html)
            if api.cfg.open_after_dl and shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", path])
            assert self.body is not None
            self.body.write(f"\nSaved → {path}")
            return

        if self.curr_file and self.curr_id and self.curr_browser_url:
            code, _ = self.courses.get(self.curr_id, ("", "Course"))
            dstdir = os.path.join(
                get_download_dir(api.cfg.download_dir),
                "Canvas",
                sanitize_filename(code or str(self.curr_id)),
            )
            os.makedirs(dstdir, exist_ok=True)
            name = self.curr_file.get("display_name") or self.curr_file.get("filename") or "syllabus.pdf"
            path = os.path.join(dstdir, sanitize_filename(name))
            browser_url = self.curr_browser_url

            def worker() -> None:
                try:
                    with api.session.get(browser_url, stream=True, timeout=api.cfg.http_timeout) as resp:
                        resp.raise_for_status()
                        with open(path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                    if api.cfg.open_after_dl and shutil.which("xdg-open"):
                        subprocess.Popen(["xdg-open", path])
                    self.app.call_from_thread(lambda: self.body and self.body.write(f"\nSaved → {path}"))
                except Exception as exc:
                    err_msg = str(exc)
                    self.app.call_from_thread(lambda: self.body and self.body.write(f"\nDownload failed: {err_msg}"))

            threading.Thread(target=worker, daemon=True).start()

    def action_browser(self) -> None:
        """Open in browser."""
        if self.curr_browser_url:
            with contextlib.suppress(Exception):
                webbrowser.open(self.curr_browser_url, new=2)
        elif self.curr_html and self.curr_id:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as f:
                f.write(self.curr_html)
                p = f.name
            _temp_files.append(p)
            with contextlib.suppress(Exception):
                webbrowser.open(f"file://{p}", new=2)

    def action_view_native(self) -> None:
        """Open PDF in native viewer (with temp file cleanup)."""
        if not self.curr_browser_url:
            return
        api = self._owner.api
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                r = api.session.get(self.curr_browser_url, timeout=api.cfg.http_timeout)
                r.raise_for_status()
                f.write(r.content)
                p = f.name
            _temp_files.append(p)
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", p])
        except Exception:
            pass

    def on_data_table_cursor_moved(self, _event: Any) -> None:
        cid = self._selected_course()
        if cid is not None and cid != self.curr_id:
            self._open_async(int(cid))

    def action_pop(self) -> None:
        self.app.pop_screen()
