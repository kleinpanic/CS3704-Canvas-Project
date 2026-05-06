# SPDX-License-Identifier: GPL-3.0-or-later
"""Keybinding registry for canvas-tui screens."""

from __future__ import annotations


class Registry:
    """Central registry for all screen keybindings.

    Each screen registers its keys at init time. Conflict detection raises
    ValueError immediately on duplicate (screen, key) pairs with different actions.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, list[tuple[str, str, str]]] = {}
        self._registered: dict[tuple[str, str], str] = {}

    def register(self, screen: str, key: str, action: str, help: str) -> None:
        existing = self._registered.get((screen, key))
        if existing is not None and existing != action:
            raise ValueError(
                f"Conflicting keybinding: screen={screen!r}, key={key!r} "
                f"already registered for action={existing!r}, "
                f"cannot register action={action!r}"
            )
        if existing is None:
            self._registered[(screen, key)] = action
            self._bindings.setdefault(screen, []).append((key, action, help))

    def get_bindings(self, screen: str) -> list[tuple[str, str, str]]:
        return list(self._bindings.get(screen, []))

    def get_help(self, screen: str) -> str:
        bindings = self._bindings.get(screen, [])
        if not bindings:
            return ""
        lines = [f"  {key:<20} {desc}" for key, _action, desc in bindings]
        return "\n".join(lines)

    def validate_all(self) -> None:
        seen: dict[tuple[str, str], str] = {}
        conflicts: list[str] = []
        for screen, entries in self._bindings.items():
            for key, action, _ in entries:
                pair = (screen, key)
                if pair in seen and seen[pair] != action:
                    conflicts.append(
                        f"screen={screen!r}, key={key!r}: {seen[pair]!r} vs {action!r}"
                    )
                else:
                    seen[pair] = action
        if conflicts:
            raise ValueError("Keybinding conflicts detected:\n" + "\n".join(conflicts))


REGISTRY = Registry()
