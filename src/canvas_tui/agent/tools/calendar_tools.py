"""Calendar tools — list, create, modify across Google Cal / Outlook / calcurses.

The actual calendar backend is selected by Config.calendar_backend. All tools
here delegate to a single CalendarAdapter that abstracts the four backends.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

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
                "start_iso": {"type": "string", "description": "ISO8601 lower bound, default = now."},
                "end_iso": {"type": "string", "description": "ISO8601 upper bound, default = +14d."},
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
            "Find blocks of free time in the calendar matching constraints. Use this BEFORE "
            "create_event to make sure you're not double-booking. Honors quiet hours, work "
            "hours, and the user's existing events."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "min_minutes": {"type": "integer", "default": 90, "description": "Minimum block length."},
                "horizon_days": {"type": "integer", "default": 7},
                "earliest_hour": {"type": "integer", "default": 7, "description": "Don't propose before this hour (24h)."},
                "latest_hour": {"type": "integer", "default": 22, "description": "Don't propose ending after this hour."},
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
        "description": "Create a calendar event. Always check find_free_blocks first.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_iso": {"type": "string"},
                "end_iso": {"type": "string"},
                "description": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
                "rationale": {"type": "string", "description": "Brief reason for this scheduling decision (logged in event description)."},
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
            "Propose modification to an existing event. Returns a 'pending' object the user "
            "must confirm via the TUI before it's applied; never silently mutates the user's "
            "calendar."
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
        "description": "Propose deletion of an event. Always returns a pending action; never silently deletes.",
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
