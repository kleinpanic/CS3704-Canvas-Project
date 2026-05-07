# SPDX-License-Identifier: GPL-3.0-or-later
"""Agentic inference loop for the Canvas Calendar Agent.

The loop drives a Gemma4-style model through the Canvas/Calendar/Study tool
registry until the model produces a final answer with no further tool calls
(or the turn budget is exhausted).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from canvas_sdk.agent_tools import dispatch, get_schemas
from canvas_sdk.backends.gemma4_backend import Gemma4Backend
from canvas_sdk.tool_parser import extract_final_answer, format_tool_result, parse_tool_calls

# Re-exported as a Union so callers can pass either backend without an extra import.
AgentBackend = Gemma4Backend  # alias kept for back-compat; GeminiBackend is duck-compatible

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = """You are the Canvas Calendar Agent, a tutor-style assistant that helps a college \
student manage their Canvas LMS coursework and weekly study schedule.

Tone: concise, friendly, action-oriented. Prefer short bullet lists.

You can call tools using this exact format inside your reply:
<|tool_call>call:tool.name{arg1: value, arg2: <|"|>quoted string<|"|>}<tool_call|>

After the tool runs, you will see the result wrapped in:
<|tool_response>response:tool.name{value:<|"|>{...}<|"|>}<tool_response|>

Rules:
- Only call tools when the user actually needs live Canvas/calendar data.
- Combine multiple tool calls in one turn when they are independent.
- Once you have enough information, write the final answer in plain prose.
  Do not include any <|tool_call> blocks in the final answer.
- Never invent assignment names, due dates, or course IDs — use tool output.

Available tools:
{tool_catalog}
"""


def _format_tool_catalog(schemas: list[dict]) -> str:
    """Render the tool registry as a compact bullet list for the system prompt."""
    lines: list[str] = []
    for entry in schemas:
        fn = entry.get("function", entry)
        name = fn.get("name", "?")
        desc = (fn.get("description") or "").strip().splitlines()[0] if fn.get("description") else ""
        params = fn.get("parameters", {}).get("properties", {}) or {}
        param_keys = ", ".join(sorted(params.keys())) if params else "—"
        lines.append(f"- {name}({param_keys}) — {desc}")
    return "\n".join(lines)


def build_system_prompt(template: str = DEFAULT_SYSTEM_PROMPT) -> str:
    """Render the default system prompt with the live tool catalog."""
    catalog = _format_tool_catalog(get_schemas())
    return template.replace("{tool_catalog}", catalog)


class CanvasAgent:
    """Drives a Gemma4 (or Gemini fallback) backend through the Canvas tool registry."""

    def __init__(self, backend, max_turns: int = 8):
        # Accepts Gemma4Backend OR GeminiBackend — both expose `.chat(messages, tools=...)`.
        self.backend = backend
        self.max_turns = max_turns

    @classmethod
    def auto(cls, max_turns: int = 8, **backend_kw):
        """Build an agent using ``ensure_model()`` to resolve the backend.

        If the model loader returns the Gemini-fallback sentinel, wires up a
        ``GeminiBackend`` instead of ``Gemma4Backend``. Extra kwargs are
        forwarded to whichever backend gets constructed (e.g. ``api_key=``).
        """
        from canvas_sdk.model_loader import GEMINI_FALLBACK_SENTINEL, ensure_model

        endpoint, model = ensure_model()
        if endpoint == GEMINI_FALLBACK_SENTINEL:
            from canvas_sdk.backends.gemini_backend import GeminiBackend

            backend = GeminiBackend(model=model, **backend_kw)
        else:
            backend = Gemma4Backend(endpoint=endpoint, model=model, **backend_kw)
        return cls(backend, max_turns=max_turns)

    def run(
        self,
        user_message: str,
        canvas_token: str = "",
        system_prompt: str | None = None,
    ) -> str:
        """Run the agent loop and return the final answer string."""
        if canvas_token:
            os.environ["CANVAS_TOKEN"] = canvas_token

        sys_prompt = system_prompt or build_system_prompt()
        schemas = get_schemas()

        messages: list[dict] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_message},
        ]

        last_text = ""
        for turn in range(self.max_turns):
            try:
                raw = self.backend.chat(messages=messages, tools=schemas)
            except Exception as exc:
                logger.exception("Backend chat call failed on turn %s", turn)
                return f"[agent error: backend call failed: {exc}]"

            last_text = raw or ""
            calls = parse_tool_calls(last_text)
            if not calls:
                return extract_final_answer(last_text)

            messages.append({"role": "assistant", "content": last_text})

            for call in calls:
                tool_name = call["tool"]
                args = call["args"]
                logger.info("agent dispatch %s args=%s", tool_name, args)
                try:
                    result: Any = dispatch(tool_name, args)
                except KeyError:
                    result = {"error": f"unknown tool: {tool_name}"}
                except Exception as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}

                if not isinstance(result, dict):
                    result = {"value": result}

                messages.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "content": format_tool_result(tool_name, result),
                    }
                )

        return extract_final_answer(last_text) or "[agent error: turn budget exhausted]"
