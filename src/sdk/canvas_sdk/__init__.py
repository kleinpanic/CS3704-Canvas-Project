from canvas_sdk.canvas import Canvas

__all__ = [
    "Canvas",
    "CanvasAgent",
    "GeminiBackend",
    "Gemma4Backend",
    "ensure_model",
]

__version__ = "1.0.0"


def __getattr__(name):
    """Lazy import of agent harness so SDK consumers without httpx still work."""
    if name == "CanvasAgent":
        from canvas_sdk.agent import CanvasAgent

        return CanvasAgent
    if name == "Gemma4Backend":
        from canvas_sdk.backends.gemma4_backend import Gemma4Backend

        return Gemma4Backend
    if name == "GeminiBackend":
        from canvas_sdk.backends.gemini_backend import GeminiBackend

        return GeminiBackend
    if name == "ensure_model":
        from canvas_sdk.model_loader import ensure_model

        return ensure_model
    raise AttributeError(f"module 'canvas_sdk' has no attribute {name!r}")
