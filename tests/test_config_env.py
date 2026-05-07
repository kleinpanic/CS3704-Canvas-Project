# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for canvas_tui.config_env (D-13)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYTHON = sys.executable


def _run_with_env(env: dict, code: str) -> subprocess.CompletedProcess:
    """Run a short Python snippet in a subprocess with the given env."""
    full_env = {**os.environ, **env}
    # Remove vars we want absent
    for key in list(full_env.keys()):
        if full_env.get(key) is None:
            del full_env[key]
    return subprocess.run(
        [_PYTHON, "-c", code],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(_REPO_ROOT),
    )


class TestCanvasBaseUrl:
    def test_missing_exits_with_code_1(self):
        """Test 1: CANVAS_BASE_URL unset → sys.exit (exit code 1)."""
        env = {"CANVAS_BASE_URL": None, "PYTHONPATH": f"{_REPO_ROOT}/src"}
        result = _run_with_env(
            env,
            "from canvas_tui.config_env import get_canvas_base_url; get_canvas_base_url()",
        )
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\n{result.stderr}"
        assert "CANVAS_BASE_URL" in result.stderr

    def test_set_returns_value(self):
        """Test 2: CANVAS_BASE_URL set → returns the value."""
        env = {
            "CANVAS_BASE_URL": "https://canvas.example.edu",
            "PYTHONPATH": f"{_REPO_ROOT}/src",
        }
        result = _run_with_env(
            env,
            "from canvas_tui.config_env import get_canvas_base_url; print(get_canvas_base_url())",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "https://canvas.example.edu"


class TestOptionalDefaults:
    def test_hf_model_default(self):
        """Test 3: CANVAS_HF_MODEL unset → default kleinpanic93 namespace."""
        env = {
            "CANVAS_BASE_URL": "https://canvas.test.example",
            "PYTHONPATH": f"{_REPO_ROOT}/src",
        }
        result = _run_with_env(
            env,
            "from canvas_tui.config_env import get_canvas_hf_model; print(get_canvas_hf_model())",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "kleinpanic93/canvas-calendar-agent-v7-dpo"

    def test_pii_space_url_default(self):
        """Test 4: CANVAS_PII_SPACE_URL unset → default PII space URL."""
        env = {
            "CANVAS_BASE_URL": "https://canvas.test.example",
            "PYTHONPATH": f"{_REPO_ROOT}/src",
        }
        result = _run_with_env(
            env,
            "from canvas_tui.config_env import get_canvas_pii_space_url; print(get_canvas_pii_space_url())",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "https://kleinpanic93-canvas-pii-scrub.hf.space"

    def test_proxy_url_default(self):
        """Test 5: CANVAS_PROXY_URL unset → default proxy URL."""
        env = {
            "CANVAS_BASE_URL": "https://canvas.test.example",
            "PYTHONPATH": f"{_REPO_ROOT}/src",
        }
        result = _run_with_env(
            env,
            "from canvas_tui.config_env import get_canvas_proxy_url; print(get_canvas_proxy_url())",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "https://cs3704-demo-proxy.kleinpanic.workers.dev"


class TestExistingTestsUnaffected:
    def test_conftest_autouse_prevents_exit(self):
        """Test 6: autouse fixture ensures canvas_tui.config imports don't exit."""
        from canvas_tui import config  # noqa: F401 — should not raise or sys.exit
