"""Tool registry for the canvas-tui agent.

Each tool exports:
  - SCHEMA: JSON-schema dict describing the function (Ollama / Gemma 4
    function-calling format)
  - call(args: dict) -> dict | list | str: actual implementation

The agent loop reads SCHEMA to advertise tools to the model, parses the
model's tool_call requests, dispatches to the matching call(), and
appends the result back to the conversation.
"""
from __future__ import annotations

from . import calendar_tools, canvas_tools, reranker_tools, study_tools

REGISTRY: dict = {}
for module in (canvas_tools, calendar_tools, reranker_tools, study_tools):
    for name in module.__all__:
        fn_obj = getattr(module, name)
        REGISTRY[fn_obj.NAME] = fn_obj


def get_schemas() -> list[dict]:
    """Return the list of tool schemas in Ollama-compatible format."""
    return [{"type": "function", "function": fn.SCHEMA} for fn in REGISTRY.values()]


def dispatch(tool_name: str, args: dict):
    """Execute a tool call by name. Raises KeyError if unknown."""
    fn = REGISTRY[tool_name]
    return fn.call(args)
