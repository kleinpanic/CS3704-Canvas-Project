# SPDX-License-Identifier: GPL-3.0-or-later
"""Centralised environment-variable reads for all canvas-tui entry points.

All consumer code that needs an env-driven constant should import from here
rather than calling os.environ.get directly.  Reads are lazy (called on
first access) so that test collection can import this module without the
process exiting when CANVAS_BASE_URL is absent.
"""

from __future__ import annotations

import os
import sys


def _require(name: str, hint: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(
            f"ERROR: {name} must be set.\n  {hint}",
            file=sys.stderr,
        )
        sys.exit(1)
    return val


def get_canvas_base_url() -> str:
    return _require(
        "CANVAS_BASE_URL",
        "e.g. export CANVAS_BASE_URL=https://canvas.yourschool.edu",
    )


def get_canvas_token() -> str:
    return os.environ.get("CANVAS_TOKEN", "")


def get_canvas_hf_model() -> str:
    return os.environ.get(
        "CANVAS_HF_MODEL",
        "kleinpanic93/canvas-calendar-agent-v7-dpo",
    )


def get_canvas_hf_space() -> str:
    return os.environ.get(
        "CANVAS_HF_SPACE",
        "kleinpanic93/canvas-calendar-agent-demo",
    )


def get_canvas_pii_space_url() -> str:
    return os.environ.get(
        "CANVAS_PII_SPACE_URL",
        "https://kleinpanic93-canvas-pii-scrub.hf.space",
    )


def get_canvas_proxy_url() -> str:
    return os.environ.get(
        "CANVAS_PROXY_URL",
        "https://cs3704-demo-proxy.kleinpanic.workers.dev",
    )


def get_canvas_llm_endpoint() -> str:
    return os.environ.get("CANVAS_LLM_ENDPOINT", "")


# Module-level aliases that evaluate lazily via __getattr__ so tests can
# import this module at collection time without CANVAS_BASE_URL set.
_LAZY = {
    "CANVAS_BASE_URL": get_canvas_base_url,
    "CANVAS_TOKEN": get_canvas_token,
    "CANVAS_HF_MODEL": get_canvas_hf_model,
    "CANVAS_HF_SPACE": get_canvas_hf_space,
    "CANVAS_PII_SPACE_URL": get_canvas_pii_space_url,
    "CANVAS_PROXY_URL": get_canvas_proxy_url,
    "CANVAS_LLM_ENDPOINT": get_canvas_llm_endpoint,
}


def __getattr__(name: str):
    if name in _LAZY:
        return _LAZY[name]()
    raise AttributeError(f"module 'canvas_tui.config_env' has no attribute {name!r}")
