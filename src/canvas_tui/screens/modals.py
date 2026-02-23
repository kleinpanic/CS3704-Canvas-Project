"""Modal prompt screens for Canvas TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class InputPrompt(ModalScreen[str]):
    """Simple text input modal."""

    BINDINGS = [("enter", "accept", "OK"), ("escape", "cancel", "Cancel")]

    def __init__(self, title: str, placeholder: str = "", default: str = "") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._default = default

    def compose(self) -> ComposeResult:
        yield Static(self._title, id="prompt-title")
        self.inp = Input(placeholder=self._placeholder, value=self._default, id="prompt-input")
        yield self.inp
        with Horizontal(id="prompt-buttons"):
            yield Button("OK", id="ok")
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.inp.focus()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(self.inp.value.strip() if ev.button.id == "ok" else "")

    def on_input_submitted(self, _ev: Input.Submitted) -> None:
        self.dismiss(self.inp.value.strip())

    def action_accept(self) -> None:
        self.dismiss(self.inp.value.strip())

    def action_cancel(self) -> None:
        self.dismiss("")


class ConfirmPath(ModalScreen[tuple[bool, str]]):
    """Confirm download path modal."""

    BINDINGS = [("enter", "accept", "Download"), ("escape", "cancel", "Cancel")]

    def __init__(self, msg: str, default_path: str) -> None:
        super().__init__()
        self.msg = msg
        self.default_path = default_path

    def compose(self) -> ComposeResult:
        yield Static(self.msg)
        self.inp = Input(value=self.default_path)
        yield self.inp
        with Horizontal():
            yield Button("Download", id="yes")
            yield Button("Cancel", id="no")

    def on_mount(self) -> None:
        self.inp.focus()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss((ev.button.id == "yes", self.inp.value.strip() if ev.button.id == "yes" else ""))

    def on_input_submitted(self, _ev: Input.Submitted) -> None:
        self.dismiss((True, self.inp.value.strip()))

    def action_accept(self) -> None:
        self.dismiss((True, self.inp.value.strip()))

    def action_cancel(self) -> None:
        self.dismiss((False, ""))


class LoadingScreen(ModalScreen[None]):
    """Loading overlay."""

    def compose(self) -> ComposeResult:
        yield Static("[b]Loading Canvas data…[/b]\n[dim]Please wait[/dim]")
