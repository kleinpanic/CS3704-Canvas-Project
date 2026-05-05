# -*- coding: utf-8 -*-

from canvas_sdk.canvas import Canvas

__all__ = ["Canvas", "CanvasAgent", "Gemma4Backend"]

__version__ = "1.0.0"


def __getattr__(name):
    """Lazy import of agent harness so SDK consumers without httpx still work."""
    if name == "CanvasAgent":
        from canvas_sdk.agent import CanvasAgent

        return CanvasAgent
    if name == "Gemma4Backend":
        from canvas_sdk.backends.gemma4_backend import Gemma4Backend

        return Gemma4Backend
    raise AttributeError(f"module 'canvas_sdk' has no attribute {name!r}")
