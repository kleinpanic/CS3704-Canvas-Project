# SPDX-License-Identifier: GPL-3.0-or-later
"""Agent tool registry for the Canvas Calendar Agent.

Each tool class exposes:
  NAME       — string function name (e.g. "canvas.get_assignments")
  SCHEMA     — JSON-schema dict in Ollama / Gemma-4 function-calling format
  call(args) — implementation; uses lazy imports so the registry is importable
               even without canvas-tui installed (schema-only mode for extension)

Usage:
    from canvas_sdk.agent_tools import REGISTRY, get_schemas, dispatch
    schemas = get_schemas()          # list[dict] for model system prompt
    result  = dispatch("canvas.get_assignments", {"horizon_days": 7})
"""

from __future__ import annotations

from . import calendar_tools, canvas_tools, reranker_tools, study_tools

REGISTRY: dict = {}
for _module in (canvas_tools, calendar_tools, study_tools, reranker_tools):
    for _name in _module.__all__:
        _fn = getattr(_module, _name)
        REGISTRY[_fn.NAME] = _fn


def get_schemas() -> list[dict]:
    """Return all tool schemas in Ollama-compatible format."""
    return [{"type": "function", "function": fn.SCHEMA} for fn in REGISTRY.values()]


def get_schema_json() -> str:
    """Return all tool schemas as a JSON string (for extension consumption)."""
    import json

    return json.dumps(get_schemas(), indent=2)


def dispatch(tool_name: str, args: dict):
    """Execute a named tool. Raises KeyError on unknown tool."""
    return REGISTRY[tool_name].call(args)
