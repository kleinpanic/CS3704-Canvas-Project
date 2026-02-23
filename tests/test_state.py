"""Tests for thread-safe state manager."""

from __future__ import annotations

import json
import os
import threading

import pytest

from canvas_tui.state import StateManager


class TestStateManager:
    def test_initial_state_has_defaults(self, sample_state_path):
        sm = StateManager(sample_state_path)
        assert sm.get("visibility") == {}
        assert sm.get("priority") == {}
        assert sm.get("pomo_end_ts") is None

    def test_set_and_get(self, sample_state_path):
        sm = StateManager(sample_state_path)
        sm.set("test_key", "test_value")
        assert sm.get("test_key") == "test_value"

    def test_persistence(self, sample_state_path):
        sm1 = StateManager(sample_state_path)
        sm1.set("persist_test", 42)

        sm2 = StateManager(sample_state_path)
        assert sm2.get("persist_test") == 42

    def test_visibility_cycle(self, sample_state_path):
        sm = StateManager(sample_state_path)
        assert sm.get_visibility("item1") == 0
        assert sm.cycle_visibility("item1") == 1
        assert sm.cycle_visibility("item1") == 2
        assert sm.cycle_visibility("item1") == 0

    def test_pomo_end(self, sample_state_path):
        sm = StateManager(sample_state_path)
        sm.set_pomo_end(1234567890.0)
        assert sm.get_pomo_end() == 1234567890.0
        sm.set_pomo_end(None)
        assert sm.get_pomo_end() is None

    def test_update_cache(self, sample_state_path):
        sm = StateManager(sample_state_path)
        items = [{"key": "test", "title": "HW1"}]
        anns = [{"key": "ann1", "title": "Announcement"}]
        sm.update_cache(items, anns)
        assert sm.get_cached_items() == items
        assert sm.get_cached_announcements() == anns

    def test_notes(self, sample_state_path):
        sm = StateManager(sample_state_path)
        assert sm.get_note("item1") == ""
        sm.set_note("item1", "Remember to review chapter 5")
        assert sm.get_note("item1") == "Remember to review chapter 5"

    def test_migrate_visibility_keys(self, sample_state_path):
        sm = StateManager(sample_state_path)
        sm.set_visibility("old_key", 2)
        migrated = sm.migrate_visibility_keys({"old_key": "new_key"})
        assert migrated == 1
        assert sm.get_visibility("new_key") == 2
        assert sm.get_visibility("old_key") == 0

    def test_thread_safety(self, sample_state_path):
        sm = StateManager(sample_state_path)
        errors = []

        def writer(n):
            try:
                for i in range(50):
                    sm.set(f"thread_{n}_{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Verify some values persisted
        assert sm.get("thread_0_49") == 49
