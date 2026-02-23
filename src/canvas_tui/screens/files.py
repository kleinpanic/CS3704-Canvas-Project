"""File manager screen — browse and download course files."""

from __future__ import annotations

import contextlib
import os
import threading
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from ..utils import get_download_dir, sanitize_filename

if TYPE_CHECKING:
    from ..app import CanvasTUI


class FileManagerScreen(Screen):
    """Browse and download course files."""

    BINDINGS = [
        ("backspace", "pop", "Back"),
        ("escape", "pop", "Back"),
        ("enter", "select", "Select/Enter folder"),
        ("w", "download", "Download selected"),
        ("W", "download_all", "Download all in folder"),
        ("space", "toggle_select", "Toggle select"),
    ]

    def __init__(self, owner_app: CanvasTUI, courses: dict[int, tuple[str, str]]) -> None:
        super().__init__()
        self._owner = owner_app
        self.courses = courses
        self._row_to_cid: list[int] = []
        self._files: list[dict[str, Any]] = []
        self._folders: list[dict[str, Any]] = []
        self._current_cid: int | None = None
        self._current_folder_id: int | None = None
        self._breadcrumb: list[tuple[int | None, str]] = []
        self._selected: set[int] = set()  # indices of selected files
        self._loading = False

    def compose(self) -> ComposeResult:
        with Vertical(id="files-root"):
            self.breadcrumb_label = Static(id="files-breadcrumb")
            yield self.breadcrumb_label
            with Horizontal(id="files-split"):
                self.course_table = DataTable(zebra_stripes=True, id="files-courses")
                yield self.course_table
                with Vertical(id="files-content"):
                    self.file_table = DataTable(zebra_stripes=True, id="files-table")
                    yield self.file_table
                    self.file_status = Static(id="files-status")
                    yield self.file_status
            yield Footer()

    def on_mount(self) -> None:
        self.course_table.clear(columns=True)
        self.course_table.add_columns("Course")
        self.course_table.cursor_type = "row"
        self._row_to_cid.clear()
        for cid, (code, _name) in sorted(self.courses.items(), key=lambda kv: (kv[1][0], kv[0])):
            self.course_table.add_row(f"{code}")
            self._row_to_cid.append(cid)
        with contextlib.suppress(Exception):
            self.course_table.cursor_coordinate = (0, 0)

        self.file_table.clear(columns=True)
        self.file_table.add_columns("[ ]", "Name", "Size", "Type", "Updated")
        self.file_table.cursor_type = "row"

        self.breadcrumb_label.update("[dim]Select a course to browse files[/dim]")
        self.file_status.update("")

        cid = self._selected_course()
        if cid is not None:
            self._load_files(cid, None)

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            event.stop()
            if self._breadcrumb:
                self._breadcrumb.pop()
                if self._breadcrumb:
                    folder_id, _ = self._breadcrumb[-1]
                    self._load_files(self._current_cid, folder_id)
                else:
                    self._load_files(self._current_cid, None)
            else:
                self.app.pop_screen()

    def _selected_course(self) -> int | None:
        row = self.course_table.cursor_row
        if row is not None and 0 <= row < len(self._row_to_cid):
            return self._row_to_cid[row]
        return None

    def on_data_table_cursor_moved(self, event: Any) -> None:
        src = getattr(event, "data_table", None) or getattr(event, "control", None)
        if src is self.course_table:
            cid = self._selected_course()
            if cid is not None and cid != self._current_cid:
                self._breadcrumb.clear()
                self._load_files(cid, None)

    def _load_files(self, cid: int | None, folder_id: int | None) -> None:
        if self._loading or cid is None:
            return
        self._loading = True
        self._current_cid = cid
        self._current_folder_id = folder_id
        self._selected.clear()
        self.file_status.update("[dim]Loading…[/dim]")

        def worker() -> None:
            try:
                api = self._owner.api
                if folder_id is not None:
                    url = api._url(f"/api/v1/folders/{folder_id}/files")
                    folders_url = api._url(f"/api/v1/folders/{folder_id}/folders")
                else:
                    url = api._url(f"/api/v1/courses/{cid}/files")
                    folders_url = api._url(f"/api/v1/courses/{cid}/folders")

                files = api.get_all(url, {"per_page": 100})
                folders = []
                with contextlib.suppress(Exception):
                    folders = api.get_all(folders_url, {"per_page": 100})

                self.app.call_from_thread(self._render_files, cid, files, folders)
            except Exception as exc:
                err = str(exc)
                self.app.call_from_thread(lambda: self.file_status.update(f"[red]Error: {err}[/red]"))
            finally:
                self._loading = False

        threading.Thread(target=worker, daemon=True).start()

    def _render_files(self, cid: int, files: list[dict[str, Any]], folders: list[dict[str, Any]]) -> None:
        self._files = files
        self._folders = folders
        self.file_table.clear()

        code, _name = self.courses.get(cid, ("?", "?"))
        bc_parts = [code] + [n for _, n in self._breadcrumb]
        self.breadcrumb_label.update(f"[b][D] {' / '.join(bc_parts)}[/b]")

        # Folders first
        for f in folders:
            fname = f.get("name") or f.get("full_name") or "folder"
            self.file_table.add_row("[D]", f"[cyan]{fname}/[/cyan]", "-", "folder", "-")

        # Then files
        for f in files:
            fname = f.get("display_name") or f.get("filename") or "file"
            size = f.get("size") or 0
            size_str = _human_size(size)
            ctype = (f.get("content-type") or f.get("mime_class") or "").split("/")[-1][:12]
            updated = (f.get("updated_at") or f.get("modified_at") or "")[:10]
            self.file_table.add_row("[ ]", fname, size_str, ctype, updated)

        total_size = sum(f.get("size") or 0 for f in files)
        self.file_status.update(
            f"{len(folders)} folders, {len(files)} files ({_human_size(total_size)})"
        )

        with contextlib.suppress(Exception):
            self.file_table.cursor_coordinate = (0, 0)

    def action_select(self) -> None:
        """Enter folder or preview file."""
        row = self.file_table.cursor_row
        if row is None:
            return

        if row < len(self._folders):
            folder = self._folders[row]
            fid = folder.get("id")
            fname = folder.get("name") or "folder"
            if fid:
                self._breadcrumb.append((fid, fname))
                self._load_files(self._current_cid, int(fid))
        # File selected — just show info for now
        else:
            fidx = row - len(self._folders)
            if 0 <= fidx < len(self._files):
                f = self._files[fidx]
                fname = f.get("display_name") or f.get("filename") or "file"
                size = _human_size(f.get("size") or 0)
                f.get("url") or f.get("download_url") or ""
                self.file_status.update(f"[b]{fname}[/b] ({size}) — press w to download")

    def action_toggle_select(self) -> None:
        """Toggle selection on current file."""
        row = self.file_table.cursor_row
        if row is None:
            return
        fidx = row - len(self._folders)
        if fidx < 0 or fidx >= len(self._files):
            return
        if fidx in self._selected:
            self._selected.discard(fidx)
            self.file_table.update_cell_at((row, 0), "[ ]")
        else:
            self._selected.add(fidx)
            self.file_table.update_cell_at((row, 0), "[x]")
        sel_count = len(self._selected)
        sel_size = sum(self._files[i].get("size") or 0 for i in self._selected)
        self.file_status.update(f"{sel_count} selected ({_human_size(sel_size)}) — press w to download")

    def action_download(self) -> None:
        """Download selected files (or current file if none selected)."""
        indices = list(self._selected)
        if not indices:
            row = self.file_table.cursor_row
            if row is not None:
                fidx = row - len(self._folders)
                if 0 <= fidx < len(self._files):
                    indices = [fidx]
        if not indices:
            return

        files_to_dl = [(self._files[i].get("display_name") or "file",
                        self._files[i].get("url") or self._files[i].get("download_url") or "",
                        self._files[i].get("size") or 0)
                       for i in indices if self._files[i].get("url") or self._files[i].get("download_url")]

        code, _ = self.courses.get(self._current_cid, ("course", ""))
        dstdir = os.path.join(get_download_dir(self._owner.api.cfg.download_dir), "Canvas", sanitize_filename(code))
        self._owner._show_confirm_path(
            f"{len(files_to_dl)} file(s). Confirm directory:",
            dstdir,
            "dl_dir",
            {"files": files_to_dl, "default": dstdir},
        )

    def action_download_all(self) -> None:
        """Download all files in current folder."""
        if not self._files:
            return
        self._selected = set(range(len(self._files)))
        self.action_download()

    def action_pop(self) -> None:
        self.app.pop_screen()


def _human_size(b: int) -> str:
    """Format bytes as human-readable."""
    if b < 1024:
        return f"{b}B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f}KB"
    if b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f}MB"
    return f"{b / (1024 * 1024 * 1024):.1f}GB"
