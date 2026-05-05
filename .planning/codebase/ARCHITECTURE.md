# Architecture

**Analysis Date:** 2026-05-05

## Pattern Overview

**Overall:** Layered Python Monorepo with Two Entry Points

**Key Characteristics:**
- Two independent executables share the Canvas SDK: TUI (`canvas-tui` CLI) and SDK (pip-installed)
- SDK is the canonical source for Canvas API data models and operations
- TUI adds a Textual-based terminal UI layer on top of the SDK
- Extension (`extension/`) is a separate JavaScript browser extension
- Monorepo with separate package manifests: `pyproject.toml` (TUI) and `sdk/pyproject.toml` (SDK)

## Layers

**SDK Layer (`sdk/canvas_sdk/`):**
- Purpose: Canonical Canvas API client — handles auth, HTTP, pagination, data models
- Contains: `canvas.py` (entry), `requester.py` (HTTP), `canvas_object.py` (data models), 50+ API endpoint modules
- Depends on: `requests`, `urllib3`
- Used by: TUI, external consumers via pip install

**TUI Layer (`src/canvas_tui/`):**
- Purpose: Terminal UI application built on Textual
- Contains: Screens (`screens/`), widgets (`widgets/`), agent tools (`agent/tools/`), adapters (`adapters/`)
- Depends on: SDK (imports `canvas_sdk.*`), Textual, caching layer
- Used by: End user CLI (`canvas-tui`)

**Duplicate API Client (`src/canvas_tui/api.py`):**
- Purpose: TUI-specific Canvas API client with custom retry + caching (standalone, does NOT use SDK)
- Contains: `CanvasAPI` class (~344 lines) — handles retries, rate limits, caching
- Note: This is the duplicate client that Phase 2 of the refactor consolidates into the SDK
- Location: `src/canvas_tui/api.py` — planned for deletion in Phase 3

## Data Flow

**TUI Execution (current, pre-refactor):**

1. User runs `canvas-tui` → `src/canvas_tui/app.py` → Textual app boots
2. `app.py` instantiates `CanvasAPI` from `src/canvas_tui/api.py` (direct API client, not SDK)
3. `CanvasAPI.get()` fetches from Canvas REST API with retry + rate-limit awareness
4. Response cached in `src/canvas_tui/cache.py` (disk-backed SQLite)
5. TUI screens render data from `CanvasAPI` + local state

**SDK Execution (target, post-refactor):**

1. User runs `canvas-tui` → `src/canvas_tui/app.py` → Textual app boots
2. `app.py` instantiates `Canvas` from `canvas_sdk.canvas` (consolidated SDK)
3. `Canvas` uses `requester.py` for HTTP operations
4. `client.py` (consolidated from `api.py`) handles retry + rate-limit + caching
5. TUI screens render data from `Canvas` + local state

**Key Abstraction: PaginatedList**

- `canvas_sdk/paginated_list.py` — Lazy paginated iteration over Canvas API list endpoints
- Pattern: Generator yielding items one-by-one, auto-fetches next page as needed
- Used by: All SDK endpoint methods (courses, assignments, users, etc.)

## Key Abstractions

**CanvasAPI (TUI layer):**
- Purpose: TUI-specific HTTP client with caching + retry
- Location: `src/canvas_tui/api.py`
- Pattern: Custom class wrapping `requests.Session`
- Note: Planned for removal in Phase 3 (consolidate into SDK)

**Canvas + Requester (SDK layer):**
- Purpose: SDK entry point + low-level HTTP transport
- Locations: `sdk/canvas_sdk/canvas.py`, `sdk/canvas_sdk/requester.py`
- Pattern: `Canvas` class orchestrates; `Requester` handles HTTP

**PaginatedList:**
- Purpose: Lazy pagination for Canvas list endpoints
- Location: `sdk/canvas_sdk/paginated_list.py`
- Pattern: Iterator protocol, auto-fetches pages on demand

**CanvasObject:**
- Purpose: Base class for all Canvas data model classes
- Location: `sdk/canvas_sdk/canvas_object.py`
- Pattern: Dataclass-like with `_setattrs` for API response hydration

## Entry Points

**TUI CLI:**
- Location: `src/canvas_tui/__main__.py` (via `canvas-tui` entry point)
- Triggers: User runs `canvas-tui` in terminal
- Responsibilities: Parse CLI args, launch Textual app

**SDK Import:**
- Location: `sdk/canvas_sdk/__init__.py`
- Triggers: `from canvas_sdk.canvas import Canvas` in any Python code
- Responsibilities: Package exports for pip-installable SDK

## Error Handling

**Strategy:** Exception hierarchy in `canvas_sdk/exceptions.py`

**Patterns:**
- `RequiredFieldMissing`, `BadRequest`, `Unauthorized`, `Forbidden`, `ResourceDoesNotExist`, `RateLimitExceeded`, `UnprocessableEntity`, `InvalidAccessToken`, `CanvasException`
- TUI's `api.py` raises generic `Exception` with string messages (pre-consolidation)
- SDK raises typed subclasses from `canvas_sdk.exceptions`

## Cross-Cutting Concerns

**Logging:**
- Uses Python `logging` module (logger instances in each module)
- No structured logging framework

**Caching:**
- TUI: `src/canvas_tui/cache.py` — disk-backed SQLite cache with TTL
- SDK: Memory-only `_cache` list in `Requester` class (no persistent cache)

**Retry:**
- TUI `api.py`: Uses `urllib3.util.retry.Retry` configured with `status_forcelist=(429,500,502,503,504)`
- SDK `requester.py`: Custom `_retry_request()` method with manual retry logic (not urllib3)

---

*Architecture analysis: 2026-05-05*
*Update when major patterns change*