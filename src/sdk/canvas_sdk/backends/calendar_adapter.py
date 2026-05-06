"""Calendar backend abstraction.

Supported backends (configured via Config.calendar_backend):
  "google"  — Google Calendar API (requires google-api-python-client + oauth2)
  "ical"    — Local / remote iCalendar file (read-only events + write to a file)
  "none"    — No-op backend; returns empty lists (testing / schema-only mode)

The backend is selected once at startup via CalendarAdapter.from_config().
All calendar tools in canvas_sdk.agent_tools.calendar_tools call this adapter.
"""

from __future__ import annotations

import abc
import datetime as dt
from typing import Any


class CalendarBackend(abc.ABC):
    """Abstract calendar backend. All methods return plain dicts (JSON-serializable)."""

    @abc.abstractmethod
    def list_events(
        self,
        calendar_id: str = "primary",
        start_iso: str | None = None,
        end_iso: str | None = None,
        include_all_day: bool = True,
    ) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    def find_free_blocks(
        self,
        min_minutes: int = 90,
        horizon_days: int = 7,
        earliest_hour: int = 7,
        latest_hour: int = 22,
        calendar_id: str = "primary",
        exclude_weekends: bool = False,
    ) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        description: str = "",
        calendar_id: str = "primary",
        rationale: str = "",
    ) -> dict[str, Any]: ...

    @abc.abstractmethod
    def propose_modification(
        self,
        event_id: str,
        title: str | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
        rationale: str = "",
    ) -> dict[str, Any]: ...

    @abc.abstractmethod
    def propose_deletion(self, event_id: str, rationale: str = "") -> dict[str, Any]: ...


class _NopBackend(CalendarBackend):
    """No-op backend for schema-only / test mode."""

    def list_events(self, **kwargs) -> list:
        return []

    def find_free_blocks(self, **kwargs) -> list:
        return []

    def create_event(self, title, start_iso, end_iso, **kwargs) -> dict:
        return {"status": "nop", "title": title, "start_iso": start_iso, "end_iso": end_iso}

    def propose_modification(self, event_id, **kwargs) -> dict:
        return {"status": "pending", "event_id": event_id, **{k: v for k, v in kwargs.items()}}

    def propose_deletion(self, event_id, rationale="") -> dict:
        return {"status": "pending_delete", "event_id": event_id, "rationale": rationale}


class GoogleCalendarBackend(CalendarBackend):
    """Google Calendar backend.

    Requires:
        pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

    OAuth2 credentials are stored at Config.google_credentials_path (default:
    ~/.config/canvas-tui/google_credentials.json). The first run opens a browser
    for the OAuth2 consent flow; subsequent runs use the stored token.
    """

    def __init__(self, credentials_path: str, token_path: str) -> None:
        self._creds_path = credentials_path
        self._token_path = token_path
        self._service = None

    def _build_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as e:
            raise ImportError(
                "Google Calendar backend requires: "
                "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
            ) from e

        import json, os

        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds = None
        if os.path.exists(self._token_path):
            with open(self._token_path) as f:
                creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self._creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self._token_path, "w") as f:
                f.write(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def _to_iso(self, dt_str: str | None) -> str | None:
        return dt_str

    def list_events(
        self,
        calendar_id: str = "primary",
        start_iso: str | None = None,
        end_iso: str | None = None,
        include_all_day: bool = True,
    ) -> list[dict]:
        svc = self._build_service()
        now = dt.datetime.now(dt.UTC)
        t_min = start_iso or now.isoformat()
        t_max = end_iso or (now + dt.timedelta(days=14)).isoformat()

        result = (
            svc.events()
            .list(
                calendarId=calendar_id,
                timeMin=t_min,
                timeMax=t_max,
                maxResults=250,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        out = []
        for ev in result.get("items", []):
            start = ev.get("start", {})
            end = ev.get("end", {})
            start_str = start.get("dateTime") or start.get("date")
            end_str = end.get("dateTime") or end.get("date")
            is_all_day = "date" in start and "dateTime" not in start
            if is_all_day and not include_all_day:
                continue
            out.append(
                {
                    "id": ev["id"],
                    "title": ev.get("summary", ""),
                    "start_iso": start_str,
                    "end_iso": end_str,
                    "all_day": is_all_day,
                    "description": ev.get("description", ""),
                    "calendar_id": calendar_id,
                }
            )
        return out

    def find_free_blocks(
        self,
        min_minutes: int = 90,
        horizon_days: int = 7,
        earliest_hour: int = 7,
        latest_hour: int = 22,
        calendar_id: str = "primary",
        exclude_weekends: bool = False,
    ) -> list[dict]:
        now = dt.datetime.now(dt.UTC)
        end = now + dt.timedelta(days=horizon_days)
        events = self.list_events(calendar_id=calendar_id, start_iso=now.isoformat(), end_iso=end.isoformat())

        busy: list[tuple[dt.datetime, dt.datetime]] = []
        for ev in events:
            if ev.get("start_iso") and ev.get("end_iso") and not ev.get("all_day"):
                s = dt.datetime.fromisoformat(ev["start_iso"].replace("Z", "+00:00"))
                e = dt.datetime.fromisoformat(ev["end_iso"].replace("Z", "+00:00"))
                busy.append((s, e))
        busy.sort()

        free_blocks = []
        cursor = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
        while cursor < end:
            if exclude_weekends and cursor.weekday() >= 5:
                cursor += dt.timedelta(days=1)
                cursor = cursor.replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
                continue

            day_start = cursor.replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
            day_end = cursor.replace(hour=latest_hour, minute=0, second=0, microsecond=0)
            slot_start = max(cursor, day_start)

            if slot_start >= day_end:
                cursor = (cursor + dt.timedelta(days=1)).replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
                continue

            for b_start, b_end in busy:
                if b_start >= day_end:
                    break
                if b_end <= slot_start:
                    continue
                if slot_start < b_start:
                    gap_minutes = int((b_start - slot_start).total_seconds() / 60)
                    if gap_minutes >= min_minutes:
                        block_end = min(slot_start + dt.timedelta(minutes=min_minutes), b_start)
                        free_blocks.append(
                            {
                                "start_iso": slot_start.isoformat(),
                                "end_iso": block_end.isoformat(),
                                "minutes": int((block_end - slot_start).total_seconds() / 60),
                            }
                        )
                slot_start = max(slot_start, b_end)

            gap_minutes = int((day_end - slot_start).total_seconds() / 60)
            if gap_minutes >= min_minutes:
                free_blocks.append(
                    {
                        "start_iso": slot_start.isoformat(),
                        "end_iso": (slot_start + dt.timedelta(minutes=min_minutes)).isoformat(),
                        "minutes": min_minutes,
                    }
                )

            cursor = (cursor + dt.timedelta(days=1)).replace(hour=earliest_hour, minute=0, second=0, microsecond=0)

        return free_blocks[:20]

    def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        description: str = "",
        calendar_id: str = "primary",
        rationale: str = "",
    ) -> dict:
        svc = self._build_service()
        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
        }
        if description or rationale:
            body["description"] = f"{description}\n[rationale: {rationale}]".strip()
        ev = svc.events().insert(calendarId=calendar_id, body=body).execute()
        return {"id": ev["id"], "title": title, "start_iso": start_iso, "end_iso": end_iso, "status": "created"}

    def propose_modification(self, event_id: str, **kwargs) -> dict:
        return {"status": "pending", "event_id": event_id, **kwargs}

    def propose_deletion(self, event_id: str, rationale: str = "") -> dict:
        return {"status": "pending_delete", "event_id": event_id, "rationale": rationale}


class ICalBackend(CalendarBackend):
    """iCalendar backend.

    Reads events from a local .ics file (or a URL). Creates events by appending
    to a writable .ics file. Suitable for use with calcurses, Thunderbird, or
    any iCal-compatible client.

    Requires: pip install icalendar recurring_ical_events
    """

    def __init__(self, ical_path: str, writeable_ical_path: str | None = None) -> None:
        self._ical_path = ical_path
        self._write_path = writeable_ical_path or ical_path

    def _load_cal(self):
        try:
            from icalendar import Calendar
        except ImportError as e:
            raise ImportError("ICalBackend requires: pip install icalendar recurring_ical_events") from e

        import urllib.request

        if self._ical_path.startswith("http"):
            with urllib.request.urlopen(self._ical_path) as r:
                data = r.read()
        else:
            with open(self._ical_path, "rb") as f:
                data = f.read()
        return Calendar.from_ical(data)

    def list_events(
        self,
        calendar_id: str = "primary",
        start_iso: str | None = None,
        end_iso: str | None = None,
        include_all_day: bool = True,
    ) -> list[dict]:
        try:
            import recurring_ical_events
        except ImportError as e:
            raise ImportError("ICalBackend requires: pip install recurring_ical_events") from e

        cal = self._load_cal()
        now = dt.datetime.now(dt.timezone.utc)
        t_start = dt.datetime.fromisoformat((start_iso or now.isoformat()).replace("Z", "+00:00"))
        t_end = dt.datetime.fromisoformat((end_iso or (now + dt.timedelta(days=14)).isoformat()).replace("Z", "+00:00"))
        events = recurring_ical_events.of(cal).between(t_start, t_end)
        out = []
        for ev in events:
            start = ev.get("DTSTART")
            end = ev.get("DTEND") or ev.get("DUE")
            if not start:
                continue
            s_dt = start.dt
            e_dt = end.dt if end else None
            is_all_day = isinstance(s_dt, dt.date) and not isinstance(s_dt, dt.datetime)
            if is_all_day and not include_all_day:
                continue
            out.append(
                {
                    "id": str(ev.get("UID", "")),
                    "title": str(ev.get("SUMMARY", "")),
                    "start_iso": s_dt.isoformat() if hasattr(s_dt, "isoformat") else str(s_dt),
                    "end_iso": e_dt.isoformat() if (e_dt and hasattr(e_dt, "isoformat")) else None,
                    "all_day": is_all_day,
                    "description": str(ev.get("DESCRIPTION", "")),
                }
            )
        return out

    def find_free_blocks(
        self,
        min_minutes: int = 90,
        horizon_days: int = 7,
        earliest_hour: int = 7,
        latest_hour: int = 22,
        calendar_id: str = "primary",
        exclude_weekends: bool = False,
    ) -> list[dict]:
        now = dt.datetime.now(dt.UTC)
        end = now + dt.timedelta(days=horizon_days)
        events = self.list_events(start_iso=now.isoformat(), end_iso=end.isoformat(), include_all_day=False)
        busy: list[tuple[dt.datetime, dt.datetime]] = []
        for ev in events:
            if ev.get("start_iso") and ev.get("end_iso"):
                s = dt.datetime.fromisoformat(str(ev["start_iso"]).replace("Z", "+00:00"))
                e = dt.datetime.fromisoformat(str(ev["end_iso"]).replace("Z", "+00:00"))
                if s.tzinfo is None:
                    s = s.replace(tzinfo=dt.timezone.utc)
                if e.tzinfo is None:
                    e = e.replace(tzinfo=dt.timezone.utc)
                busy.append((s, e))
        busy.sort()

        free_blocks = []
        cursor = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
        while cursor < end and len(free_blocks) < 20:
            if exclude_weekends and cursor.weekday() >= 5:
                cursor = (cursor + dt.timedelta(days=1)).replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
                continue
            slot_start = cursor.replace(hour=max(cursor.hour, earliest_hour), minute=0, second=0, microsecond=0)
            day_end = cursor.replace(hour=latest_hour, minute=0, second=0, microsecond=0)
            for b_s, b_e in busy:
                if b_s >= day_end:
                    break
                if b_e <= slot_start:
                    continue
                if slot_start < b_s:
                    gap = int((b_s - slot_start).total_seconds() / 60)
                    if gap >= min_minutes:
                        free_blocks.append(
                            {
                                "start_iso": slot_start.isoformat(),
                                "end_iso": (slot_start + dt.timedelta(minutes=min_minutes)).isoformat(),
                                "minutes": min_minutes,
                            }
                        )
                slot_start = max(slot_start, b_e)
            gap = int((day_end - slot_start).total_seconds() / 60)
            if gap >= min_minutes:
                free_blocks.append(
                    {
                        "start_iso": slot_start.isoformat(),
                        "end_iso": (slot_start + dt.timedelta(minutes=min_minutes)).isoformat(),
                        "minutes": min_minutes,
                    }
                )
            cursor = (cursor + dt.timedelta(days=1)).replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
        return free_blocks

    def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        description: str = "",
        calendar_id: str = "primary",
        rationale: str = "",
    ) -> dict:
        try:
            from icalendar import Calendar, Event
        except ImportError as e:
            raise ImportError("ICalBackend requires: pip install icalendar") from e

        import uuid

        uid = str(uuid.uuid4())
        ev = Event()
        ev.add("SUMMARY", title)
        ev.add("DTSTART", dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00")))
        ev.add("DTEND", dt.datetime.fromisoformat(end_iso.replace("Z", "+00:00")))
        ev.add("UID", uid)
        if description or rationale:
            ev.add("DESCRIPTION", f"{description}\nrationale: {rationale}".strip())

        import os

        if os.path.exists(self._write_path):
            with open(self._write_path, "rb") as f:
                cal = Calendar.from_ical(f.read())
        else:
            cal = Calendar()
            cal.add("PRODID", "-//canvas-tui//calendar-agent//EN")
            cal.add("VERSION", "2.0")

        cal.add_component(ev)
        with open(self._write_path, "wb") as f:
            f.write(cal.to_ical())

        return {"id": uid, "title": title, "start_iso": start_iso, "end_iso": end_iso, "status": "created"}

    def propose_modification(self, event_id: str, **kwargs) -> dict:
        return {"status": "pending", "event_id": event_id, **kwargs}

    def propose_deletion(self, event_id: str, rationale: str = "") -> dict:
        return {"status": "pending_delete", "event_id": event_id, "rationale": rationale}


class CalendarAdapter:
    """Factory — returns the right CalendarBackend based on Config.calendar_backend."""

    @classmethod
    def from_config(cls) -> CalendarBackend:
        from canvas_tui.config import load_config

        cfg = load_config()
        backend = getattr(cfg, "calendar_backend", "none")

        if backend == "google":
            import os

            creds_path = getattr(
                cfg, "google_credentials_path", os.path.expanduser("~/.config/canvas-tui/google_credentials.json")
            )
            token_path = getattr(cfg, "google_token_path", os.path.expanduser("~/.config/canvas-tui/google_token.json"))
            return GoogleCalendarBackend(creds_path, token_path)

        if backend == "ical":
            ical_path = getattr(cfg, "ical_path", os.path.expanduser("~/.local/share/canvas-tui/calendar.ics"))
            write_path = getattr(cfg, "ical_write_path", ical_path)
            return ICalBackend(ical_path, write_path)

        return _NopBackend()
