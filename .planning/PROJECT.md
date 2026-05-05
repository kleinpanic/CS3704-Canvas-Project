# CS3704-REFACTOR - Canvas SDK Refactoring Project

## What This Is

Brownfield Python monorepo containing a Canvas LMS TUI application (`canvas_tui`) and a Canvas SDK (`canvas_sdk`). The project is being refactored to improve code organization, consolidate duplicate API clients, improve test coverage, and enhance CI/CD.

## Core Value

Consolidate the two parallel Canvas API clients into a single, well-tested SDK that serves both the TUI and any future consumers, with comprehensive test coverage and robust CI/CD.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Move `sdk/canvas_sdk/` into `src/canvas_sdk/` to consolidate monorepo structure
- [ ] Consolidate the two parallel Canvas API clients (src/canvas_tui/api.py and sdk/canvas_sdk/canvas.py)
- [ ] Improve SDK test coverage with unit and integration tests
- [ ] Enhance CI/CD pipeline with automated testing and deployment

### Out of Scope

- [Breaking changes to TUI public API] — TUI refactoring is out of scope for this phase; consolidate SDK first
- [New features] — No new Canvas API features; this is a structural refactor
- [Documentation rewrite] — Existing docs are sufficient; focus on code structure

## Context

**Current codebase structure:**
- `src/canvas_tui/` — Terminal UI application with its own Canvas API client (`api.py`)
- `sdk/canvas_sdk/` — Official Canvas SDK with class-based API clients (`canvas.py`, `canvas_object.py`)
- `tests/` — Pytest-based test suite for TUI components
- `extension/` — Browser extension with its own `canvas-client.js`
- Parallel Canvas API clients create maintenance burden and potential inconsistencies

**Key technical observations:**
1. `src/canvas_tui/api.py` has ~344 lines with custom retry logic, rate-limit handling, caching
2. `sdk/canvas_sdk/canvas.py` has ~1310 lines with a `Requester` class and `PaginatedList` pattern
3. Duplicate Canvas API functionality across both clients
4. SDK tests only cover `agent_tools/` subdirectory; broader SDK coverage needed

## Constraints

- **Tech Stack**: Python 3.13+, pytest, requests library — maintain compatibility
- **Backward Compatibility**: TUI must continue to function after SDK consolidation
- **Git History**: Preserve commit history during file moves via `git mv`

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Move SDK into src/ | Consolidate monorepo, single import path | — Pending |
| Consolidate API clients | Eliminate duplicate code, single source of truth | — Pending |
| Focus on test coverage | Ensure refactored code is well-tested | — Pending |

---

*Last updated: 2026-05-05 after initialization*