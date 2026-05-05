"""Calendar agent tools — list, create, modify events via the configured calendar backend."""
from __future__ import annotations

__all__ = ["ListEvents", "FindFreeBlocks", "CreateEvent", "ModifyEvent", "DeleteEvent"]


def _adapter():
    from canvas_tui.agent.backends.calendar_adapter import CalendarAdapter
    return CalendarAdapter.from_config()


class ListEvents:
    NAME = "calendar.list_events"
    SCHEMA = {
        "name": NAME,
        "description": "List calendar events in a window (default: next 14 days).",
        "parameters": {
            "type": "object",
            "properties": {
                "calendar_id": {"type": "string", "default": "primary"},
                "start_iso": {"type": "string", "description": "ISO8601 lower bound; defaults to now."},
                "end_iso": {"type": "string", "description": "ISO8601 upper bound; defaults to +14d."},
                "include_all_day": {"type": "boolean", "default": True},
            },
            "required": [],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        return _adapter().list_events(**args)


class FindFreeBlocks:
    NAME = "calendar.find_free_blocks"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Find free blocks in the calendar matching constraints. Always call this "
            "BEFORE create_event to avoid double-booking. Respects quiet hours and "
            "existing events."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "min_minutes": {"type": "integer", "default": 90, "description": "Minimum block length in minutes."},
                "horizon_days": {"type": "integer", "default": 7},
                "earliest_hour": {"type": "integer", "default": 7, "description": "24h clock — never propose before this hour."},
                "latest_hour": {"type": "integer", "default": 22, "description": "24h clock — never propose blocks ending after this hour."},
                "calendar_id": {"type": "string", "default": "primary"},
                "exclude_weekends": {"type": "boolean", "default": False},
            },
            "required": [],
        },
    }

    @staticmethod
    def call(args: dict) -> list[dict]:
        return _adapter().find_free_blocks(**args)


class CreateEvent:
    NAME = "calendar.create_event"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Create a calendar event. Always call find_free_blocks first to confirm "
            "the slot is available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_iso": {"type": "string"},
                "end_iso": {"type": "string"},
                "description": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
                "rationale": {
                    "type": "string",
                    "description": "Brief reason for this scheduling decision (logged in event description).",
                },
            },
            "required": ["title", "start_iso", "end_iso"],
        },
    }

    @staticmethod
    def call(args: dict) -> dict:
        return _adapter().create_event(**args)


class ModifyEvent:
    NAME = "calendar.modify_event"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Propose a modification to an existing event. Returns a pending object "
            "that the user must confirm in the TUI — never silently mutates the calendar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "title": {"type": "string"},
                "start_iso": {"type": "string"},
                "end_iso": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["event_id"],
        },
    }

    @staticmethod
    def call(args: dict) -> dict:
        return _adapter().propose_modification(**args)


class DeleteEvent:
    NAME = "calendar.delete_event"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Propose deletion of a calendar event. Returns a pending action; "
            "never silently deletes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["event_id", "rationale"],
        },
    }

    @staticmethod
    def call(args: dict) -> dict:
        return _adapter().propose_deletion(**args)
