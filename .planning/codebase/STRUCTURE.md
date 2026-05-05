# Codebase Structure

**Analysis Date:** 2026-05-05

## Directory Layout

```
CS3704-Canvas-Project/
├── src/                        # TUI application (pip-installable as "canvas-tui")
│   ├── canvas_tui/            # Main package
│   │   ├── __init__.py
│   │   ├── __main__.py         # CLI entry point ("python -m canvas_tui")
│   │   ├── app.py             # Textual application root
│   │   ├── api.py             # Duplicate Canvas API client (to be deleted)
│   │   ├── cache.py           # Disk-backed response cache
│   │   ├── config.py          # Configuration loading
│   │   ├── cli.py             # CLI argument parsing
│   │   ├── state.py           # Application state
│   │   ├── normalize.py       # Data normalization utilities
│   │   ├── filtering.py       # Course/assignment filtering
│   │   ├── notifications.py   # Notification management
│   │   ├── ics.py             # ICS calendar export
│   │   ├── reranker.py        # Local reranking (AI extra)
│   │   ├── models.py          # TUI-specific data models
│   │   ├── models/            # Sub-package models
│   │   ├── screens/           # Textual screen implementations
│   │   ├── widgets/          # Reusable Textual widgets
│   │   ├── commands/         # Command registry
│   │   ├── agent/             # Agent tools
│   │   │   └── tools/        # Canvas, study, calendar, reranker tools
│   │   ├── adapters/          # Database/cache adapters
│   │   ├── core/              # Interface definitions
│   │   └── rmp/              # RateMyProfessors integration
│   └── canvas_sdk/           # ⭐ SDK MOVE TARGET: sdk/canvas_sdk/ moves here (Phase 1)
├── sdk/                       # SDK package (will be removed after Phase 1 move)
│   └── canvas_sdk/           # 50+ API modules + __init__.py
├── tests/                     # Test suite (pytest)
│   ├── conftest.py           # Shared fixtures
│   ├── test_*.py             # Unit tests (test_api.py, test_cache.py, etc.)
│   └── rmp/                  # RMP-specific tests
├── extension/                 # Browser extension (JavaScript)
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   └── canvas-client.js     # Independent JS API client
├── docs-site/                 # mkdocs documentation site
├── docs/                      # Developer documentation (md)
├── scripts/                   # Build/release scripts
├── tools/                     # Utility scripts
├── .github/workflows/         # CI/CD workflows
├── pyproject.toml             # TUI package manifest
├── sdk/pyproject.toml         # SDK package manifest (separate pip-installable)
├── requirements.txt           # TUI dependencies
└── Makefile                   # Build automation
```

## Directory Purposes

**src/canvas_tui/ — TUI Application**
- Purpose: Terminal UI application for Canvas LMS
- Contains: Textual screens, widgets, state management, CLI entry
- Key files: `app.py` (root), `api.py` (duplicate client), `cache.py` (response cache)
- Subdirectories: `screens/`, `widgets/`, `agent/tools/`, `adapters/`, `models/`

**sdk/canvas_sdk/ — Canvas SDK (Phase 1 move target)**
- Purpose: Canonical Canvas API SDK (pip-installable independently)
- Contains: 50+ API endpoint modules, base classes, requester, exceptions
- Key files: `canvas.py` (entry), `requester.py` (HTTP), `canvas_object.py` (base model)
- Note: Moves to `src/canvas_sdk/` in Phase 1 of refactor

**tests/ — Test Suite**
- Purpose: Pytest-based unit and integration tests
- Contains: `conftest.py` (shared fixtures), 20+ `test_*.py` files
- Note: SDK tests live in `sdk/canvas_sdk/agent_tools/tests/` (separate test suite)

**extension/ — Browser Extension**
- Purpose: Chrome/Firefox extension for Canvas web interface
- Contains: JS/CSS files, `manifest.json`
- Note: Has independent `canvas-client.js` (separate from Python clients)

## Key File Locations

**Entry Points:**
- `src/canvas_tui/__main__.py` — CLI entry (`python -m canvas_tui`)
- `src/canvas_tui/app.py` — Textual TUI application root
- `sdk/canvas_sdk/__init__.py` — SDK package entry (`from canvas_sdk import ...`)

**Configuration:**
- `src/canvas_tui/config.py` — Config loading from env vars
- `pyproject.toml` — TUI package config (pytest, setuptools)
- `sdk/pyproject.toml` — SDK package config
- `ruff.toml` — Linter configuration (line-length: 120)

**SDK Core (Phase 1 move target):**
- `sdk/canvas_sdk/canvas.py` — `Canvas` class (main SDK entry)
- `sdk/canvas_sdk/requester.py` — HTTP client with auth
- `sdk/canvas_sdk/canvas_object.py` — Base class for all endpoint models
- `sdk/canvas_sdk/paginated_list.py` — Lazy pagination
- `sdk/canvas_sdk/exceptions.py` — Exception hierarchy

**TUI Core:**
- `src/canvas_tui/api.py` — Duplicate Canvas API client (~344 lines)
- `src/canvas_tui/cache.py` — Response cache (SQLite-backed)
- `src/canvas_tui/state.py` — Application state
- `src/canvas_tui/screens/` — Textual screens (grades, analytics, weekview, etc.)

## Naming Conventions

**Files:**
- Python: `snake_case.py` for modules, `PascalCase.py` for classes
- Test files: `test_*.py` (collocated with source via `tests/` directory)
- Config files: `*.toml`, `*.json`, `*.yml`

**Directories:**
- snake_case for all package directories
- Plural names for collections: `screens/`, `widgets/`, `models/`, `tools/`

**Classes:**
- PascalCase: `CanvasAPI`, `Canvas`, `PaginatedList`, `CanvasObject`
- No prefix: No `I` or `T` prefixes

## Where to Add New Code

**New TUI Feature:**
- Primary code: `src/canvas_tui/screens/` (screen) or `src/canvas_tui/widgets/` (widget)
- Tests: `tests/test_*.py`
- Config if needed: `src/canvas_tui/config.py`

**New SDK Endpoint:**
- Primary code: `src/canvas_sdk/` (after Phase 1) or `sdk/canvas_sdk/` (before Phase 1)
- Tests: `sdk/canvas_sdk/agent_tools/tests/` (current) or new `tests/canvas_sdk/` (post-refactor)
- Model file: One file per endpoint (e.g., `course.py`, `assignment.py`)

**New API Client Feature (pre-consolidation):**
- Primary code: `src/canvas_tui/api.py` (TUI client) or `sdk/canvas_sdk/canvas.py` (SDK client)
- Note: Phase 2 consolidates into single `canvas_sdk/client.py`

## Special Directories

**sdk/canvas_sdk/agent_tools/tests/**
- Purpose: SDK agent tools test suite (separate from TUI tests)
- Note: Will be consolidated into `tests/canvas_sdk/` in Phase 4

**src/canvas_tui/agent/**
- Purpose: Agent backend tools (calendar adapter, canvas tools, study tools)
- Note: Uses SDK's `canvas_sdk` package (will update after Phase 1 move)

---

*Structure analysis: 2026-05-05*
*Update when directory structure changes*