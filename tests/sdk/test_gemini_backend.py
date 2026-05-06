# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Gemini fallback backend.

The real google-generativeai SDK isn't available in CI by default, so we
inject a stub module before importing the backend. The tests cover:

- the system prompt contains every tool name in the registry,
- the backend constructor reads GOOGLE_API_KEY from env,
- chat() merges the protocol prompt with any incoming `system` message
  and forwards user content to a mocked GenerativeModel.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_genai(monkeypatch):
    """Install a fake google.generativeai module before backend import."""
    fake_genai = types.ModuleType("google.generativeai")

    captured: dict = {}

    def _configure(api_key=None):
        captured["api_key"] = api_key

    class _FakeChat:
        def __init__(self, history):
            captured["history"] = history

        def send_message(self, content):
            captured["sent"] = content
            resp = MagicMock()
            resp.text = "stubbed response"
            return resp

    class _FakeModel:
        def __init__(self, model_name, system_instruction, generation_config):
            captured["model_name"] = model_name
            captured["system_instruction"] = system_instruction
            captured["generation_config"] = generation_config

        def start_chat(self, history):
            return _FakeChat(history)

    fake_genai.configure = _configure
    fake_genai.GenerativeModel = _FakeModel

    fake_google = types.ModuleType("google")
    fake_google.generativeai = fake_genai

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    # Drop any cached import of the backend so it picks up the stub.
    for mod in list(sys.modules):
        if mod.startswith("canvas_sdk.backends.gemini_backend"):
            sys.modules.pop(mod, None)

    return captured


def test_system_prompt_contains_all_18_tools(stub_genai):
    from canvas_sdk.agent_tools import REGISTRY
    from canvas_sdk.backends.gemini_backend import build_gemini_system_prompt

    prompt = build_gemini_system_prompt()
    assert len(REGISTRY) == 18  # sanity
    for tool_name in REGISTRY:
        assert tool_name in prompt, f"system prompt missing tool: {tool_name}"


def test_system_prompt_explains_tool_call_format(stub_genai):
    from canvas_sdk.backends.gemini_backend import build_gemini_system_prompt

    prompt = build_gemini_system_prompt()
    assert "<|tool_call>" in prompt
    assert "<tool_call|>" in prompt
    assert '<|"|>' in prompt


def test_constructor_reads_env_var(monkeypatch, stub_genai):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-from-env")

    from canvas_sdk.backends.gemini_backend import GeminiBackend

    GeminiBackend()
    assert stub_genai["api_key"] == "test-key-from-env"


def test_constructor_explicit_api_key_wins(monkeypatch, stub_genai):
    monkeypatch.setenv("GOOGLE_API_KEY", "from-env")

    from canvas_sdk.backends.gemini_backend import GeminiBackend

    GeminiBackend(api_key="explicit")
    assert stub_genai["api_key"] == "explicit"


def test_constructor_raises_without_key(monkeypatch, stub_genai):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    from canvas_sdk.backends.gemini_backend import GeminiBackend

    with pytest.raises(RuntimeError):
        GeminiBackend()


def test_chat_merges_system_prompt_and_returns_text(monkeypatch, stub_genai):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    from canvas_sdk.backends.gemini_backend import GeminiBackend

    backend = GeminiBackend()
    out = backend.chat(
        messages=[
            {"role": "system", "content": "You are the Canvas Calendar Agent."},
            {"role": "user", "content": "What's due this week?"},
        ]
    )
    assert out == "stubbed response"
    sysinst = stub_genai["system_instruction"]
    assert "Canvas Calendar Agent" in sysinst
    assert "<|tool_call>" in sysinst
    assert stub_genai["sent"] == "What's due this week?"
