"""
Command pattern for Canvas Deadline Tracker.

Actions are decoupled from the TUI app so the same commands can be
executed from the TUI, a background worker, or a future browser extension.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.interfaces import CacheBackend, CanvasClient


# ── Command Interface ──────────────────────────────────────────────────────────

class Command(ABC):
    """Base command. Subclasses implement execute()."""

    @abstractmethod
    def execute(self) -> CommandResult:
        """Run the command and return a result."""
        ...

    @abstractmethod
    def description(self) -> str:
        """Human-readable description for logs/UI."""
        ...


@dataclass
class CommandResult:
    """Standard result wrapper for all commands."""
    ok: bool
    data: dict | list | None = None
    error: str | None = None
    cached: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def raise_on_error(self) -> None:
        """Raise ValueError if the command failed."""
        if not self.ok:
            raise ValueError(self.error or "Command failed")


# ── Concrete Commands ─────────────────────────────────────────────────────────

class RefreshCoursesCommand(Command):
    """Fetch and cache all enrolled courses."""
    name = "refresh_courses"

    def __init__(self, client: CanvasClient, cache: CacheBackend):
        self._client = client
        self._cache = cache

    def execute(self) -> CommandResult:
        try:
            courses, scores = self._client.fetch_course_snapshot()
            self._cache.set("courses_snapshot", (courses, scores))
            return CommandResult(ok=True, data={"count": len(courses)})
        except Exception as e:
            return CommandResult(ok=False, error=str(e))

    def description(self) -> str:
        return "Refresh courses"


class FetchAssignmentsCommand(Command):
    """Fetch assignments for a specific course."""
    name = "fetch_assignments"

    def __init__(self, client: CanvasClient, cache: CacheBackend, course_id: int):
        self._client = client
        self._cache = cache
        self._course_id = course_id

    def execute(self) -> CommandResult:
        cached = self._cache.get(f"assignments:{self._course_id}")
        if cached:
            return CommandResult(ok=True, data=cached, cached=True)
        try:
            # CanvasAPI returns dicts, not Assignment objects
            assignments = self._client.fetch_assignment_details(
                self._course_id, 0
            )
            return CommandResult(ok=True, data=assignments)
        except Exception as e:
            return CommandResult(ok=False, error=str(e))

    def description(self) -> str:
        return f"Fetch assignments for course {self._course_id}"


class FetchUpcomingCommand(Command):
    """Fetch upcoming assignments across all courses."""
    name = "fetch_upcoming"

    def __init__(self, client: CanvasClient, cache: CacheBackend):
        self._client = client
        self._cache = cache

    def execute(self) -> CommandResult:
        cached = self._cache.get("upcoming")
        if cached:
            return CommandResult(ok=True, data=cached, cached=True)
        try:
            items = self._client.fetch_planner_items()
            self._cache.set("upcoming", items, ttl=300)
            return CommandResult(ok=True, data=items)
        except Exception as e:
            return CommandResult(ok=False, error=str(e))

    def description(self) -> str:
        return "Fetch upcoming assignments"


class ValidateTokenCommand(Command):
    """Validate the stored Canvas token."""
    name = "validate_token"

    def __init__(self, client: CanvasClient):
        self._client = client

    def execute(self) -> CommandResult:
        try:
            ok = self._client.validate_token()
            return CommandResult(ok=ok, data={"valid": ok})
        except Exception as e:
            return CommandResult(ok=False, error=str(e))

    def description(self) -> str:
        return "Validate Canvas token"


# ── Command Registry ───────────────────────────────────────────────────────────

class CommandRegistry:
    """Maps command names to Command instances. Used by both TUI and extension."""

    def __init__(self):
        self._commands: dict[str, Command] = {}

    def register(self, name: str, cmd: Command) -> None:
        self._commands[name] = cmd

    def execute(self, name: str) -> CommandResult:
        if name not in self._commands:
            return CommandResult(ok=False, error=f"Unknown command: {name}")
        return self._commands[name].execute()

    def list_commands(self) -> list[str]:
        return list(self._commands.keys())
