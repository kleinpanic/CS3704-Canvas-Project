# Coding Conventions

**Analysis Date:** 2026-05-05

## Naming Patterns

**Files:**
- snake_case.py for all Python modules
- test files: `test_*.py` in `tests/` directory
- Config: `*.toml`, `*.json`, `*.yml`

**Functions:**
- snake_case for all functions and methods
- No special prefix for async functions

**Variables:**
- snake_case for variables and instance attributes
- `_prefix` for private/internal attributes (by convention)
- UPPER_SNAKE_CASE for module-level constants

**Types:**
- PascalCase for classes and type names
- `|` union syntax for type annotations (Python 3.10+)
- Dataclasses for structured data (via `@dataclass`)

## Code Style

**Formatting:**
- Tool: `ruff` (configured in `ruff.toml` / `ruff.toml`)
- Line length: 120 characters
- Target Python: 3.11+ (`target-version = "py311"`)
- Import sorting: enabled via ruff (I rule)

**Linting:**
- Rules enabled: `E`, `F`, `W`, `I`, `UP`, `B`, `SIM`, `RUF`
- Ignored: `E501` (line length handled by formatter), `E741`, `B008`, `SIM108`, `RUF012`
- Per-file ignores: `tests/*` skips `B` and `SIM`

**Type Checking:**
- Tool: `mypy` (in dev dependencies)
- Config: `pyproject.toml` has pytest config, mypy configured separately

## Import Organization

**Order:**
1. Standard library
2. Third-party packages
3. Local application imports (relative)

**Pattern:** `from __future__ import annotations` at top of most files

**SDK imports:**
- `from canvas_sdk.canvas import Canvas` — main entry
- `from canvas_sdk.x import Y` — individual modules
- TUI imports SDK as `canvas_sdk.*`

**TUI imports:**
- Relative imports within `canvas_tui` package: `from . import module`
- Cross-package: `from canvas_sdk import ...` (after SDK is installed/available)

## Error Handling

**Patterns:**
- TUI (`api.py`): Raises generic `Exception` with string messages
- SDK: Typed exception hierarchy in `canvas_sdk/exceptions.py`
  - `CanvasException` (base), `RequiredFieldMissing`, `BadRequest`, `Unauthorized`, `Forbidden`, `ResourceDoesNotExist`, `RateLimitExceeded`, `UnprocessableEntity`, `InvalidAccessToken`
- Phase 2 refactor: TUI will migrate to SDK's typed exceptions

**Retry:**
- TUI `api.py`: `urllib3.util.retry.Retry` with `status_forcelist=(429,500,502,503,504)`
- SDK `requester.py`: Custom `_retry_request()` with explicit retry loop

## Comments

**When to Comment:**
- Module-level docstrings (all major files)
- Class docstrings (Canvas API client classes)
- Method docstrings with `:param` / `:returns` for complex methods

**Pattern:** Google-style docstrings (used in `canvas_sdk/` modules)

**TODO Comments:**
- Plain `TODO:` style (no username/issue format enforced)

## Function Design

**Size:** Keep functions focused; multiple smaller functions preferred

**Parameters:** Type hints on all parameters and return values

**Return Values:** Explicit `return` statements; no implicit `None`

## Module Design

**SDK Structure:**
- One file per Canvas endpoint class: `account.py`, `course.py`, `assignment.py`, etc.
- Base classes in `canvas_object.py`, `canvas.py`, `requester.py`
- `__init__.py` re-exports main classes

**TUI Structure:**
- `screens/` — Textual screen implementations
- `widgets/` — Reusable UI components
- `models/` — Data model classes
- `agent/tools/` — Agent tool implementations

**Exports:**
- Named exports via `__init__.py`
- Public API surface: `Canvas`, `PaginatedList`, `CanvasObject` in SDK

---

*Convention analysis: 2026-05-05*
*Update when patterns change*