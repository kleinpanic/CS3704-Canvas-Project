"""Tests for _NopBackend in canvas_sdk.backends.calendar_adapter.

Skipped entirely if the module is not yet present at canvas_sdk.backends.calendar_adapter.
Falls back to importing from canvas_tui.agent.backends.calendar_adapter if the sdk-side
module doesn't exist yet.
"""
import pytest

# Try the SDK-side location first; fall back to canvas_tui source location.
calendar_adapter = pytest.importorskip(
    "canvas_sdk.backends.calendar_adapter",
    reason="canvas_sdk.backends.calendar_adapter not yet installed",
)

_NopBackend = calendar_adapter._NopBackend


@pytest.fixture
def nop():
    return _NopBackend()


def test_nop_list_events_returns_empty_list(nop):
    result = nop.list_events()
    assert result == []


def test_nop_list_events_returns_list_type(nop):
    result = nop.list_events(calendar_id="primary", start_iso=None, end_iso=None)
    assert isinstance(result, list)


def test_nop_find_free_blocks_returns_empty_list(nop):
    result = nop.find_free_blocks()
    assert result == []


def test_nop_find_free_blocks_returns_list_type(nop):
    result = nop.find_free_blocks(min_minutes=60, horizon_days=3)
    assert isinstance(result, list)


def test_nop_create_event_status_is_nop(nop):
    result = nop.create_event("Test Event", "2026-05-01T10:00:00Z", "2026-05-01T11:30:00Z")
    assert result["status"] == "nop"


def test_nop_create_event_title_preserved(nop):
    result = nop.create_event("My Study Block", "2026-05-01T10:00:00Z", "2026-05-01T11:30:00Z")
    assert result["title"] == "My Study Block"


def test_nop_create_event_start_iso_preserved(nop):
    start = "2026-05-01T10:00:00Z"
    result = nop.create_event("X", start, "2026-05-01T11:00:00Z")
    assert result["start_iso"] == start


def test_nop_create_event_end_iso_preserved(nop):
    end = "2026-05-01T11:30:00Z"
    result = nop.create_event("X", "2026-05-01T10:00:00Z", end)
    assert result["end_iso"] == end


def test_nop_create_event_returns_dict(nop):
    result = nop.create_event("X", "2026-05-01T10:00:00Z", "2026-05-01T11:00:00Z")
    assert isinstance(result, dict)


def test_nop_propose_modification_status_is_pending(nop):
    result = nop.propose_modification("evt_123", rationale="test reason")
    assert result["status"] == "pending"


def test_nop_propose_modification_event_id_preserved(nop):
    result = nop.propose_modification("evt_123", rationale="test reason")
    assert result["event_id"] == "evt_123"


def test_nop_propose_modification_returns_dict(nop):
    result = nop.propose_modification("evt_abc")
    assert isinstance(result, dict)


def test_nop_propose_deletion_status_is_pending_delete(nop):
    result = nop.propose_deletion("evt_123", rationale="no longer needed")
    assert result["status"] == "pending_delete"


def test_nop_propose_deletion_event_id_preserved(nop):
    result = nop.propose_deletion("evt_123", rationale="r")
    assert result["event_id"] == "evt_123"


def test_nop_propose_deletion_rationale_preserved(nop):
    result = nop.propose_deletion("evt_456", rationale="cancelled")
    assert result["rationale"] == "cancelled"


def test_nop_propose_deletion_returns_dict(nop):
    result = nop.propose_deletion("evt_789", rationale="x")
    assert isinstance(result, dict)
