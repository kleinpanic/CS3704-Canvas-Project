# Claims Audit — What We Promised vs What We Have

Last updated: 2026-04-14
Status: IN PROGRESS — several gaps identified

---

## PM3 Claims (High-Level Design)

### Command Pattern (PROMISED — NOT IMPLEMENTED)

**Promised in PM3:**
```
class Command:
    def execute(self, app: "CanvasTUI") -> None:
        raise NotImplementedError

class RefreshDataCommand(Command): ...
class SwitchScreenCommand(Command): ...
class OpenURLCommand(Command): ...
```

**Current reality:** `app.py` uses `action_*` methods and `on_key` handlers. No `Command` base class, no `execute()` protocol. The PM3 doc's pseudocode is not implemented.

**Gap severity:** HIGH — this is a documented architectural claim.

---

### MVC Pattern (IMPLEMENTED)

**Promised:** `models.py`, `api.py`, `state.py`, `cache.py` as Model layer; `screens/` + `widgets/` as View; `app.py` + `cli.py` as Controller.

**Current reality:** Matches the promise. ✓

---

### Design Pattern: Repository Pattern (PROMISED — PARTIAL)

**Promised:** Transparent offline/online operation, consistent error handling, rate limiting.

**Current reality:** Exists in `api.py` with rate limiting, but not structured as an explicit Repository interface. PARTIAL ✓

---

## PM4 / Extension Roadmap Claims

### Phase 1: Core Abstraction (NOT IMPLEMENTED)

| Promise | Status |
|----------|--------|
| `CanvasClient` abstract interface | NOT DONE |
| `AuthManager` protocol | NOT DONE |
| `CacheBackend` abstraction (SQLite vs IndexedDB) | NOT DONE — `cache.py` is one monolithic SQLite class |
| `NotificationCenter` interface | NOT DONE |
| `src/canvas_tui/core/` directory | NOT DONE — models/ split done, but no core/ protocol layer |
| `src/canvas_tui/adapters/` directory | NOT DONE |
| Architecture Decision Records (ADRs) | NOT DONE |

**Gap severity:** HIGH — blocking the browser extension path

---

### Feature Parity Matrix (EXTENSION ROADMAP)

| Feature | TUI Status |
|---------|-----------|
| Dashboard | ✓ |
| Assignments | ✓ |
| Grades | ✓ |
| Announcements | ✓ |
| Files | ✓ |
| Calendar | ✓ |
| Offline Cache (SQLite) | ✓ |
| Notifications (terminal) | ✓ |
| Pomodoro | ✓ |
| Browser Extension | NOT STARTED |
| Desktop GUI | NOT STARTED |

Most TUI features are implemented. Browser extension not started — documented as future work. ✓

---

## Visual Claims (PM3 Wireframe)

### Dashboard Layout (MOSTLY MET)

**Wireframe showed:**
- `[Logo: CANVAS TUI]` + `Course Scores (Bar Chart)` — ✓ bar chart exists
- `Due Soon (8 items)` with color-coded `[RED]OVERDUE`, `[YELLOW]<12h`, `[GREEN]Today` — ✓ type badges now added
- `Grade Completion (Gauges)` — ✓ gauges implemented
- `Grade Trends (Sparklines)` — ✓ sparklines implemented
- Keybindings footer `[r] Refresh [Enter] Details [o] Open [q] Quit` — PARTIAL (some keys differ)

**Visual fidelity note:** The current dashboard now uses box-drawing headers and type badges — close to the wireframe intent.

---

## Claims Not Yet Addressed

### 1. Command Pattern (HIGH PRIORITY)
Implement `Command` base class and refactor `action_*` methods into proper commands.

### 2. Core Abstraction for Extension (HIGH PRIORITY — blocks PM4 requirements)
Extract `CanvasClient`, `CacheBackend`, `AuthManager` as explicit interfaces in `core/` directory.

### 3. ICS Export (IMPLEMENTED — verify)
PM3 says "trigger external actions like opening a browser or downloading a file." ICS export is implemented.

### 4. Rate Limiting + Retry (IMPLEMENTED)
Repository pattern promised "rate limiting and retry logic" — exists in `api.py`.

### 5. Offline Cache (IMPLEMENTED)
"SQLite persistence layer" — `cache.py` is implemented.

---

## What We CAN Claim as Implemented

- MVC architecture (as documented)
- Offline-first SQLite cache
- TUI with dashboard, grades, week view, courses, announcements, files, syllabi
- Grade trends sparklines and completion gauges
- What-if calculator in grades
- ICS export
- Pomodoro timer
- Command bar with structured filtering
- Fuzzy search
- CI/CD pipeline with tests, coverage, AI fixup workflows
- Team documentation (CONTRIBUTORS.md, MAINTAINERS.md, DEVELOPER_GUIDE.md)
- Visual polish (type badges, box-drawing headers)

---

## Priority Fixes for Class Compliance

1. **Command pattern** — refactor `app.py` to use `Command` base class with `execute(app)` protocol
2. **Core interfaces** — extract `CanvasClient` protocol for extension readiness (even if not fully wired to browser)

These are the concrete architectural claims that need to be addressed.

---

_This document is the source of truth for our claims audit. Update as gaps are filled._