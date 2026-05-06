"""OpenAI-compatible LLM backend for Gemma4 inference.

Talks to any OpenAI-compatible chat-completions endpoint (vLLM, llama.cpp, forge,
spark-proxy, etc.). Default points at the local spark-proxy router on :18080.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import httpx
except ImportError as exc:  # pragma: no cover - import-time guard
    raise ImportError("Gemma4Backend requires httpx. Install with: pip install httpx") from exc


class Gemma4Backend:
    """OpenAI-compatible backend for Gemma4 models.

    Sends chat-completions requests and returns the raw assistant string so
    the caller can run the Gemma4 tool-call parser on it. Tool schemas are
    forwarded as the `tools` field for backends that support native tool use,
    but Gemma4 emits its own ``<|tool_call>...<tool_call|>`` format inside the
    text content regardless.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:18080/v1",
        model: str = "google/gemma-4-e2b-it",
        api_key: str = os.environ.get("SPARK_API_KEY", "forge"),
        timeout: float = 60.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kw: Any,
    ) -> str:
        """Send a chat-completions request and return the assistant text."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        payload.update(kw)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.endpoint}/chat/completions"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return json.dumps(data)
