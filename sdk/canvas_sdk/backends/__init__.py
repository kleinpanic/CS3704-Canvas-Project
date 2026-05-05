"""LLM and calendar backend adapters for the Canvas Calendar Agent."""

from __future__ import annotations


def __getattr__(name):
    if name == "Gemma4Backend":
        from canvas_sdk.backends.gemma4_backend import Gemma4Backend

        return Gemma4Backend
    raise AttributeError(f"module 'canvas_sdk.backends' has no attribute {name!r}")


__all__ = ["Gemma4Backend"]
