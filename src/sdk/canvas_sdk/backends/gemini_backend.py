# SPDX-License-Identifier: GPL-3.0-or-later
"""Gemini fallback backend for the Canvas Calendar Agent.

Used when no fine-tuned Gemma4 model is available locally or via HF. The
backend wraps Google's `google-generativeai` client and injects an extra
system instruction that teaches Gemini the Gemma4 ``<|tool_call>...<tool_call|>``
protocol so the rest of the harness (parser, dispatcher) can be reused
without modification.

Auth: reads ``GOOGLE_API_KEY`` from the environment (or accepts an explicit
``api_key`` arg). Default model is ``gemini-2.5-flash`` — cheap, fast, and
strong enough at instruction following to emit the tool-call format reliably.
"""

from __future__ import annotations

import json
import os
from typing import Any

GEMINI_TOOL_PROTOCOL = """\
You are bridging into a Gemma4-trained tool-calling harness. The harness can
ONLY parse tool calls in the exact Gemma4 textual format below. Do NOT use
Google's native function-calling — emit the tool call as plain text inside
your reply.

Tool-call format (literal characters, no markdown fences):
<|tool_call>call:tool.name{arg1: value, arg2: <|"|>quoted string<|"|>}<tool_call|>

After execution the harness will replay the result to you wrapped in:
<|tool_response>response:tool.name{value:<|"|>{...json...}<|"|>}<tool_response|>

Rules:
- Quote every string argument with the ``<|"|>...<|"|>`` sentinel — ordinary
  double quotes will be rejected.
- Issue independent calls in the same turn when possible (parser handles
  multiple blocks per reply).
- Once you have enough information, write the final answer in plain prose
  with NO ``<|tool_call>`` blocks remaining.
- Never invent assignment names, due dates, course IDs, or grades — every
  fact must trace back to a tool result.

Available tools:
{tool_catalog}
"""


def _format_tool_catalog(schemas: list[dict]) -> str:
    """Render the tool registry as a compact bullet list (mirrors agent.py)."""
    lines: list[str] = []
    for entry in schemas:
        fn = entry.get("function", entry)
        name = fn.get("name", "?")
        desc = (fn.get("description") or "").strip().splitlines()[0] if fn.get("description") else ""
        params = fn.get("parameters", {}).get("properties", {}) or {}
        param_keys = ", ".join(sorted(params.keys())) if params else "—"
        lines.append(f"- {name}({param_keys}) — {desc}")
    return "\n".join(lines)


def build_gemini_system_prompt(schemas: list[dict] | None = None) -> str:
    """Build the Gemini-specific tool-call protocol prompt.

    Returns the full instruction text the caller should prepend (or merge)
    into the agent's system prompt before sending to Gemini.
    """
    if schemas is None:
        from canvas_sdk.agent_tools import get_schemas

        schemas = get_schemas()
    catalog = _format_tool_catalog(schemas)
    return GEMINI_TOOL_PROTOCOL.replace("{tool_catalog}", catalog)


class GeminiBackend:
    """Gemini chat backend that speaks the Gemma4 tool-call protocol.

    Mirrors the ``Gemma4Backend.chat()`` signature so ``CanvasAgent`` can
    swap between them without code changes.
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "GeminiBackend requires google-generativeai. Install with: pip install canvas-sdk[gemini]"
            ) from exc

        self._genai = genai
        self.model = model
        self.timeout = timeout
        key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GeminiBackend needs GOOGLE_API_KEY (or GEMINI_API_KEY) in env, or pass api_key= explicitly."
            )
        genai.configure(api_key=key)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **_: Any,
    ) -> str:
        """Send a chat turn to Gemini, return raw assistant text.

        Merges any incoming `system` message with the Gemma4 protocol prompt
        so Gemini emits ``<|tool_call>`` blocks the harness can parse.
        """
        protocol = build_gemini_system_prompt(tools)

        sys_chunks: list[str] = [protocol]
        history: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                sys_chunks.append(content)
            elif role == "user":
                history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
            elif role == "tool":
                # Replay tool results as a synthetic user turn so Gemini sees them.
                name = msg.get("name", "tool")
                history.append(
                    {
                        "role": "user",
                        "parts": [f"[tool result for {name}]\n{content}"],
                    }
                )

        system_instruction = "\n\n".join(c for c in sys_chunks if c)

        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_instruction,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )

        if not history:
            history = [{"role": "user", "parts": [""]}]

        # Send the final user turn fresh; everything before is conversation history.
        last = history[-1]
        chat = model.start_chat(history=history[:-1])
        try:
            resp = chat.send_message(last["parts"][0])
        except Exception as exc:
            return json.dumps({"error": f"gemini call failed: {exc}"})

        try:
            return resp.text or ""
        except (ValueError, AttributeError):
            # `resp.text` can raise if the candidate was filtered; fall back.
            try:
                return resp.candidates[0].content.parts[0].text or ""
            except Exception:
                return ""
