# Technology Stack

**Analysis Date:** 2026-05-05

## Languages

**Primary:**
- Python 3.11+ — All application code, SDK, TUI, and tests

**Secondary:**
- JavaScript/TypeScript — Browser extension (`extension/`)

## Runtime

**Environment:**
- Python 3.11–3.13 (tested across 3.11, 3.12, 3.13)
- Node.js — Only for extension/build tooling

**Package Manager:**
- pip (via `pip install -e .`)
- npm for extension (`package-lock.json` present)
- Lockfile: `pyproject.toml` (setuptools) + `package-lock.json`

## Frameworks

**Core:**
- Textual 0.40+ — TUI framework (`canvas_tui.app`)
- requests 2.28+ — HTTP client for Canvas API
- urllib3 2.0+ — Retry and rate-limit logic

**Testing:**
- pytest — Test runner (configured in `pyproject.toml`)
- pytest-cov — Coverage enforcement

**Build/Dev:**
- setuptools 68+ — Package building
- ruff — Linting and formatting
- mypy — Static type checking
- mkdocs + mkdocs-material — Documentation site

## Key Dependencies

**Critical:**
- `requests>=2.28` — Canvas API HTTP calls (TUI `api.py` and SDK `requester.py`)
- `urllib3>=2.0` — Retry strategy (`Retry` class), connection pooling
- `textual>=0.40` — Terminal UI framework

**CLI/TUI:**
- `keyring>=23.0` — Optional secure token storage (`[keyring]` extra)
- `llama-cpp-python>=0.3` — Optional local GGUF inference for reranker (`[ai]` extra)

**SDK-specific:**
- `canvas_sdk/` — Self-contained SDK package (separate `sdk/pyproject.toml`)
- SDK uses same `requests` + `urllib3` stack as TUI

## Configuration

**Environment:**
- `CANVAS_TOKEN` — Canvas API access token
- `CANVAS_BASE_URL` — Canvas instance root URL
- `TZ` — Timezone for deadline display
- `EXPORT_DIR` — Output directory for ICS/exports

**Build:**
- `pyproject.toml` — Package metadata, dependencies, pytest config
- `sdk/pyproject.toml` — Separate package manifest for `canvas_sdk`
- `ruff.toml` / `.ruff.toml` — Linter config (line-length: 120)

## Platform Requirements

**Development:**
- macOS/Linux/Windows (Python 3.11+)
- No external services required (offline-capable when cached)

**Production:**
- Distributed as pip-installable package (`canvas-tui`)
- SDK independently pip-installable from `sdk/` subdirectory

---

*Stack analysis: 2026-05-05*
*Update after major dependency changes*