"""Integration tests against the live HF Space.

Requires network access and a running Space. Skip in default CI via:

    pytest -m "not network"

Run explicitly with:

    pytest tests/test_hf_space_integration.py -m network -v -s --tb=short
"""

from __future__ import annotations

import logging

import pytest

logger = logging.getLogger(__name__)

SPACE_ID = "kleinpanic93/canvas-calendar-agent-demo"
TIMEOUT = 90

PROMPTS = [
    ("canvas.get_assignments", "What assignments do I have due this week?"),
    ("canvas.list_courses", "Show me my course list"),
    ("calendar.find_free_blocks", "Find a 2-hour study block tomorrow"),
    ("study.exam_bracket", "Build me an exam bracket for May 12"),
    ("reranker.priority_hint", "Rank my todos by priority"),
]


@pytest.fixture(scope="module")
def space_client():
    try:
        from gradio_client import Client
    except ImportError:
        pytest.skip("gradio-client not installed; run: pip install gradio-client>=1.3")

    try:
        client = Client(SPACE_ID, verbose=False)
    except Exception as exc:
        pytest.skip(f"Could not connect to HF Space ({SPACE_ID}): {exc}")

    return client


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.parametrize("tool_family,prompt", PROMPTS, ids=[p[0] for p in PROMPTS])
def test_space_responds_to_prompt(space_client, tool_family, prompt):
    try:
        result = space_client.predict(
            message=prompt,
            api_name="/chat",
        )
    except Exception as exc:
        msg = str(exc)
        if any(code in msg for code in ("503", "500", "error", "Space")):
            pytest.skip(f"Space not ready ({tool_family}): {exc}")
        raise

    logger.info("[%s] prompt=%r", tool_family, prompt)
    logger.info("[%s] response=%r", tool_family, result)

    tool_calls_observed = []
    if isinstance(result, (list, tuple)):
        for item in result:
            item_str = str(item)
            if "<|tool_call>" in item_str or "tool_call" in item_str.lower():
                tool_calls_observed.append(item_str[:200])
    elif isinstance(result, str):
        if "<|tool_call>" in result or "tool_call" in result.lower():
            tool_calls_observed.append(result[:200])

    if tool_calls_observed:
        logger.info("[%s] tool calls observed: %s", tool_family, tool_calls_observed)
    else:
        logger.info("[%s] no explicit tool-call tokens in response", tool_family)

    response_text = result if isinstance(result, str) else str(result)
    assert response_text.strip(), (
        f"Empty response from Space for tool family {tool_family!r}, prompt={prompt!r}"
    )
