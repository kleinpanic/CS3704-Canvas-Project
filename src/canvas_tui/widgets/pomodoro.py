"""Pomodoro timer widget."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from textual.widgets import Static

from ..utils import notify


class Pomodoro(Static):
    """Pomodoro timer with thread-safe updates and completion notification."""

    def __init__(self, on_state_change: Callable[[float | None], None] | None = None) -> None:
        super().__init__(id="pomodoro")
        self._timer_lock = threading.Lock()
        self._end_ts: float | None = None
        self._ticker_thread: threading.Thread | None = None
        self._stop = False
        self._on_state_change = on_state_change
        self.update("[dim]Pomodoro: stopped[/dim]")

    def start(self, minutes: int) -> None:
        """Start a new timer for the given minutes."""
        with self._timer_lock:
            self._end_ts = time.time() + max(1, int(minutes)) * 60
            self._stop = False
            if self._on_state_change:
                self._on_state_change(self._end_ts)
            if not self._ticker_thread or not self._ticker_thread.is_alive():
                self._ticker_thread = threading.Thread(target=self._run, daemon=True)
                self._ticker_thread.start()
            else:
                self._safe_update(self._render_status())

    def resume_until(self, end_ts: float) -> None:
        """Resume a timer from a saved end timestamp."""
        with self._timer_lock:
            self._end_ts = float(end_ts)
            self._stop = False
            if not self._ticker_thread or not self._ticker_thread.is_alive():
                self._ticker_thread = threading.Thread(target=self._run, daemon=True)
                self._ticker_thread.start()
            self._safe_update(self._render_status())

    def stop(self) -> None:
        """Stop the timer."""
        with self._timer_lock:
            self._end_ts = None
            self._stop = True
            if self._on_state_change:
                self._on_state_change(None)
            self._safe_update("[dim]Pomodoro: stopped[/dim]")

    def _safe_update(self, text: str) -> None:
        """Thread-safe widget update."""
        try:
            self.app.call_from_thread(self.update, text)
        except Exception:
            with contextlib.suppress(Exception):
                self.update(text)

    def _render_status(self) -> str:
        """Build status line with progress bar."""
        if self._end_ts is None:
            return "[dim]Pomodoro: stopped[/dim]"
        remaining = max(0, int(self._end_ts - time.time()))
        m, s = divmod(remaining, 60)
        total = max(1, int(self._end_ts - (time.time() - remaining)))
        bar_len = 28
        filled = int(bar_len * (1 - remaining / total))
        bar = "█" * filled + "░" * (bar_len - filled)
        return f"🍅 Pomodoro: {m:02d}:{s:02d}  {bar}"

    @property
    def title_suffix(self) -> str:
        """Short timer string for the app title bar."""
        if self._end_ts is None:
            return ""
        remaining = max(0, int(self._end_ts - time.time()))
        m, s = divmod(remaining, 60)
        return f" 🍅 {m:02d}:{s:02d}"

    def _run(self) -> None:
        """Tick loop running on background thread."""
        while True:
            with self._timer_lock:
                if self._stop:
                    self._safe_update("[dim]Pomodoro: stopped[/dim]")
                    self._update_app_title()
                    break
                text = self._render_status()
                if "00:00" in text and self._end_ts is not None:
                    self._safe_update("[green bold]🍅 Pomodoro done![/green bold]")
                    notify("Pomodoro", "Time is up! 🍅")
                    # Ring terminal bell
                    with contextlib.suppress(Exception):
                        print("\a", end="", flush=True)
                    self._end_ts = None
                    if self._on_state_change:
                        self._on_state_change(None)
                    self._update_app_title()
                    break
                self._safe_update(text)
                self._update_app_title()
            time.sleep(1)

    def _update_app_title(self) -> None:
        """Update the app title bar with timer info."""
        try:
            suffix = self.title_suffix
            base = "Canvas TUI"
            self.app.call_from_thread(setattr, self.app, "title", f"{base}{suffix}")
        except Exception:
            pass
