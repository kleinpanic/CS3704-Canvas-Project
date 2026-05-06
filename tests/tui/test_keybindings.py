# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the keybinding Registry module."""

import pytest

from canvas_tui.keybindings import Registry


class TestRegistryConflict:
    def test_same_screen_same_key_different_action_raises(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        with pytest.raises(ValueError, match="Conflicting keybinding"):
            reg.register("home", "q", "different_action", "Different")

    def test_same_screen_same_key_same_action_is_ok(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        reg.register("home", "q", "quit", "Quit again")


class TestRegistryNoConflict:
    def test_same_key_different_screens_no_error(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        reg.register("rmp", "q", "pop_screen", "Back")

    def test_different_keys_same_screen_no_error(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        reg.register("home", "r", "refresh", "Refresh")


class TestGetHelp:
    def test_returns_nonempty_string_with_keys(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        reg.register("home", "r", "refresh", "Refresh")
        result = reg.get_help("home")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "q" in result
        assert "r" in result

    def test_unknown_screen_returns_empty_string(self):
        reg = Registry()
        result = reg.get_help("nonexistent")
        assert result == ""


class TestGetBindings:
    def test_returns_exactly_registered_bindings(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        reg.register("home", "r", "refresh", "Refresh")
        bindings = reg.get_bindings("home")
        assert len(bindings) == 2
        keys = [b[0] for b in bindings]
        assert "q" in keys
        assert "r" in keys

    def test_returns_copy_not_reference(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        b1 = reg.get_bindings("home")
        b1.append(("x", "extra", "Extra"))
        b2 = reg.get_bindings("home")
        assert len(b2) == 1


class TestValidateAll:
    def test_no_conflicts_passes(self):
        reg = Registry()
        reg.register("home", "q", "quit", "Quit")
        reg.register("rmp", "q", "pop_screen", "Back")
        reg.validate_all()

    def test_conflicts_found_by_validate_all(self):
        reg = Registry()
        reg._bindings["home"] = [("q", "quit", "Quit"), ("q", "other", "Other")]
        reg._registered[("home", "q")] = "quit"
        with pytest.raises(ValueError):
            reg.validate_all()
