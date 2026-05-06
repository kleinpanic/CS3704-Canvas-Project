# SPDX-License-Identifier: GPL-3.0-or-later
__all__ = [
    "Assignment",
    "CanvasAgent",
    "CanvasClient",
    "CanvasException",
    "CanvasServerError",
    "Conflict",
    "Course",
    "DiscussionTopic",
    "Enrollment",
    "Forbidden",
    "GeminiBackend",
    "Gemma4Backend",
    "InvalidAccessToken",
    "PlannerNote",
    "RateLimitExceeded",
    "ResourceNotFound",
    "Todo",
    "UnprocessableEntity",
    "User",
    "ensure_model",
]

__version__ = "2.0.0"


def __getattr__(name):
    """Lazy import so submodules with optional deps (httpx, google) don't
    break ``import canvas_sdk`` for consumers that only need part of the SDK.
    """
    if name == "CanvasClient":
        from canvas_sdk.client import CanvasClient

        return CanvasClient
    if name in ("Course", "Assignment", "DiscussionTopic", "Todo", "PlannerNote", "Enrollment", "User"):
        import canvas_sdk.entities as _entities

        return getattr(_entities, name)
    if name in (
        "CanvasException",
        "InvalidAccessToken",
        "Forbidden",
        "ResourceNotFound",
        "Conflict",
        "UnprocessableEntity",
        "RateLimitExceeded",
        "CanvasServerError",
    ):
        import canvas_sdk.exceptions as _exceptions

        return getattr(_exceptions, name)
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
