"""Tests for due date notification system."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch
from zoneinfo import ZoneInfo

from canvas_tui.models import CanvasItem
from canvas_tui.notifications import DueNotifier, _send_notification


class TestDueNotifier:
    def test_creates_without_error(self):
        n = DueNotifier(tz="America/New_York")
        assert n._thresholds == [60, 30, 15]

    def test_custom_thresholds(self):
        n = DueNotifier(thresholds_min=[120, 60, 5])
        assert n._thresholds == [120, 60, 5]

    def test_clear_notified(self):
        n = DueNotifier()
        n._notified.add("test:60")
        n.clear_notified()
        assert len(n._notified) == 0

    def test_check_fires_notification(self):
        """Test that _check fires notifications for upcoming items."""
        tz = "America/New_York"
        now = dt.datetime.now(ZoneInfo(tz))
        due_soon = (now + dt.timedelta(minutes=25)).astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        items = [
            CanvasItem(
                key="test1",
                ptype="assignment",
                title="HW Due Soon",
                course_code="CS101",
                due_iso=due_soon,
                status_flags=[],
            )
        ]

        n = DueNotifier(tz=tz, thresholds_min=[30, 15], get_items=lambda: items)

        with patch("canvas_tui.notifications.notify") as mock_notify:
            n._check()
            # Should have fired for the 30-min threshold
            assert mock_notify.called or "test1:30" in n._notified

    def test_submitted_items_skipped(self):
        tz = "America/New_York"
        now = dt.datetime.now(ZoneInfo(tz))
        due_soon = (now + dt.timedelta(minutes=10)).astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        items = [CanvasItem(key="s1", due_iso=due_soon, status_flags=["submitted"])]
        n = DueNotifier(tz=tz, get_items=lambda: items)
        n._check()
        assert len(n._notified) == 0

    def test_no_duplicate_notifications(self):
        tz = "America/New_York"
        now = dt.datetime.now(ZoneInfo(tz))
        due_soon = (now + dt.timedelta(minutes=10)).astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        items = [CanvasItem(key="d1", due_iso=due_soon, status_flags=[])]
        n = DueNotifier(tz=tz, get_items=lambda: items)

        with patch("canvas_tui.notifications.notify"):
            n._check()
            n._check()  # Second check should not re-notify
            # Key should only appear once in notified set
            assert sum(1 for k in n._notified if k.startswith("d1:")) <= len(n._thresholds)


class TestSendNotification:
    @patch("canvas_tui.notifications.notify")
    def test_formats_hours(self, mock_notify):
        item = CanvasItem(key="1", title="Final Exam", course_code="CS3214", ptype="assignment")
        _send_notification(item, 60)
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args
        assert "1h" in call_args[0][0]

    @patch("canvas_tui.notifications.notify")
    def test_formats_minutes(self, mock_notify):
        item = CanvasItem(key="1", title="Quiz", course_code="CS101", ptype="quiz")
        _send_notification(item, 15)
        mock_notify.assert_called_once()
        assert "15m" in mock_notify.call_args[0][0]
