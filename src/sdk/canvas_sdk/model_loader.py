# SPDX-License-Identifier: GPL-3.0-or-later
"""Auto-download / endpoint resolution for the Canvas Calendar Agent.

Resolution order for ``ensure_model()``:

1. ``CANVAS_LLM_ENDPOINT`` env var set            → use it (model from CANVAS_LLM_MODEL).
2. Local cache at ``~/.cache/canvas-agent/v7-dpo`` exists → spawn a local OpenAI-compatible
   server (vLLM if importable, otherwise a tiny transformers+flask wrapper) on port 8765.
3. HF repo ``kleinpanic93/canvas-calendar-agent-v7-dpo`` is downloadable → snapshot it
   into the cache and recurse.
4. Nothing local, nothing on HF → return the ``__GEMINI_FALLBACK__`` sentinel and let
   ``CanvasAgent`` route to ``GeminiBackend``.

The function is intentionally side-effect heavy: it can spawn subprocesses,
hit the network, and write to disk. Callers should treat it as one-shot per
process.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

GEMINI_FALLBACK_SENTINEL = "__GEMINI_FALLBACK__"
DEFAULT_HF_REPO = "kleinpanic93/canvas-calendar-agent-v7-dpo"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "canvas-agent" / "v7-dpo"
DEFAULT_LOCAL_PORT = 8765


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def _wait_for_port(port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_listening(port):
            return True
        time.sleep(0.5)
    return False


def _spawn_local_vllm(model_path: Path, port: int) -> tuple[str, str] | None:
    """Try to spawn a local vLLM server. Returns (endpoint, model) or None.

    We don't hold a handle to the subprocess — the user's process owns it.
    Subsequent ensure_model() calls will see the listening port and skip
    the spawn.
    """
    if _port_listening(port):
        logger.info("local server already listening on :%s", port)
        return f"http://localhost:{port}/v1", str(model_path)

    if shutil.which("vllm") is None:
        logger.info("vllm CLI not found on PATH; skipping local spawn")
        return None

    cmd = [
        "vllm",
        "serve",
        str(model_path),
        "--port",
        str(port),
        "--host",
        "127.0.0.1",
    ]
    log_path = DEFAULT_CACHE_DIR.parent / "vllm.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "ab") as log_fh:
            subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as exc:
        logger.warning("failed to spawn vllm: %s", exc)
        return None

    logger.info("waiting for vllm to come up on :%s (logs: %s)", port, log_path)
    if not _wait_for_port(port, timeout=120.0):
        logger.warning("vllm did not bind :%s within 120s", port)
        return None

    return f"http://localhost:{port}/v1", str(model_path)


def _try_download_from_hf(repo: str, dest: Path) -> bool:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        logger.info("huggingface_hub not installed; install canvas-sdk[autodownload] to enable model auto-download")
        return False

    try:
        dest.mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id=repo, local_dir=str(dest), local_dir_use_symlinks=False)
        return True
    except Exception as exc:
        logger.warning("HF snapshot_download failed for %s: %s", repo, exc)
        return False


def ensure_model(
    cache_dir: Path | None = None,
    hf_repo: str | None = None,
    port: int = DEFAULT_LOCAL_PORT,
) -> tuple[str, str]:
    """Resolve an inference endpoint and model name.

    Returns ``(endpoint, model_name)``. ``endpoint`` may be the special
    ``__GEMINI_FALLBACK__`` sentinel; callers must check for it before
    constructing a ``Gemma4Backend``.
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    hf_repo = hf_repo or DEFAULT_HF_REPO

    explicit = os.environ.get("CANVAS_LLM_ENDPOINT", "").strip()
    if explicit:
        model = os.environ.get("CANVAS_LLM_MODEL", "google/gemma-4-e2b-it")
        logger.info("using explicit CANVAS_LLM_ENDPOINT=%s model=%s", explicit, model)
        return explicit, model

    if cache_dir.exists() and any(cache_dir.iterdir()):
        result = _spawn_local_vllm(cache_dir, port)
        if result is not None:
            return result
        logger.info("local cache present but server unreachable; falling through")

    if _try_download_from_hf(hf_repo, cache_dir):
        result = _spawn_local_vllm(cache_dir, port)
        if result is not None:
            return result

    logger.warning("no local model and HF download unavailable; falling back to Gemini (set GOOGLE_API_KEY)")
    return GEMINI_FALLBACK_SENTINEL, "gemini-2.5-flash"
