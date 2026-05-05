# Codebase Concerns

**Analysis Date:** 2026-05-05

## Tech Debt

**Duplicate Canvas API clients:**
- Issue: Two independent Canvas API clients exist — `src/canvas_tui/api.py` (~344 lines) and `sdk/canvas_sdk/requester.py` + `canvas.py` (~1310 lines)
- Why: TUI originally built without SDK; SDK added later but TUI not migrated
- Impact: Maintenance burden, potential inconsistencies, duplicate retry/caching logic
- Fix approach: Phase 2 consolidation creates `canvas_sdk/client.py` combining best patterns; Phase 3 deletes `api.py`

**Inconsistent retry logic:**
- Issue: TUI `api.py` uses `urllib3.Retry`; SDK `requester.py` uses manual retry loop
- Files: `src/canvas_tui/api.py` (lines ~50-80), `sdk/canvas_sdk/requester.py` (manual `_retry_request`)
- Why: Different authors at different times
- Fix approach: Unify in Phase 2 `client.py` using `urllib3.Retry` (more robust)

**Inconsistent caching:**
- Issue: TUI has disk-backed SQLite cache (`src/canvas_tui/cache.py`); SDK has memory-only `_cache` list in `Requester`
- Files: `src/canvas_tui/cache.py`, `sdk/canvas_sdk/requester.py` (line ~65)
- Why: Different use cases (offline TUI vs API client)
- Fix approach: `canvas_sdk/cache.py` in Phase 2 with thread-safe atomic writes

**SDK test isolation gap:**
- Issue: SDK tests only cover `agent_tools/` subdirectory; core SDK modules (`canvas.py`, `requester.py`, `paginated_list.py`) have no tests
- Files: `sdk/canvas_sdk/agent_tools/tests/` (only this dir has tests)
- Why: Tests added incrementally, core modules not covered
- Fix approach: Phase 4 adds unit tests for `client.py`, `cache.py`, `config.py`, `paginated_list.py` (≥80% coverage)

## Known Bugs

**No known bugs currently tracked.** If bugs are discovered during refactoring, add them here.

## Security Considerations

**Canvas token in environment variable:**
- Risk: `CANVAS_TOKEN` stored as plain text environment variable (visible via `ps eww`)
- Current mitigation: `keyring` extra available for secure storage
- Recommendations: Default to keyring in production; document secure setup

**RateMyProfessors scraping:**
- Risk: RMP integration (`src/canvas_tui/rmp/client.py`) has no official API — scraping may break
- Current mitigation: None (RMP may block or change structure)
- Recommendations: Consider RateMyProfessors official API or alternative data source

## Performance Bottlenecks

**Paginated list iteration:**
- Problem: `PaginatedList` fetches one page at a time; large course with 500+ items = 5-10 sequential requests
- File: `sdk/canvas_sdk/paginated_list.py`
- Cause: Simple next-page detection via `Link` header
- Improvement path: Prefetch/cache pages (Phase 2 `client.py` caching helps)

**TUI cache SQLite writes:**
- Problem: Cache writes are synchronous on each API response
- File: `src/canvas_tui/cache.py` (SQLite `execute()` called in main request path)
- Cause: Synchronous writes block response
- Improvement path: Phase 2 `canvas_sdk/cache.py` with async write queue

## Fragile Areas

**SDK `canvas.py` — large entry point:**
- Why fragile: 1310-line `Canvas` class with all endpoint access methods
- Common failures: Easy to accidentally break API compatibility for one endpoint
- Safe modification: Test all endpoint methods after any change
- Test coverage: None currently (Phase 4 adds tests)

**TUI `api.py` — duplicate client:**
- Why fragile: Will be deleted in Phase 3 — must work until then
- Common failures: Any changes must keep both clients working
- Safe modification: No new features; only bug fixes before Phase 3

**PaginatedList iterator:**
- Why fragile: Iterator protocol with auto-fetch; consumer must not exhaust while iterating
- File: `sdk/canvas_sdk/paginated_list.py`
- Common failures: Consuming list while network error mid-iteration
- Safe modification: Don't change while iterating; wrap in try/except for network errors

## Dependencies at Risk

**Textual framework:**
- Risk: TUI tightly coupled to Textual; breaking changes in Textual could break TUI
- Impact: `canvas_tui/app.py` and all `screens/` depend on Textual
- Mitigation: `textual>=0.40` pinned in dependencies

**requests library:**
- Risk: `requests` is mature and stable; low risk
- Impact: Both clients depend on `requests.Session`

## Missing Critical Features

**SDK persistent cache:**
- Problem: SDK has no disk-backed cache — each process starts fresh
- Current workaround: TUI has its own cache, but SDK consumers have none
- Blocks: SDK users can't do offline mode or reduce API calls
- Implementation complexity: Medium (Phase 2 `canvas_sdk/cache.py` addresses this)

**SDK configuration management:**
- Problem: SDK requires manual `base_url` + `access_token` passed to every `Canvas()` constructor
- Current workaround: Users manage their own config
- Blocks: Hard to share SDK with consistent defaults
- Implementation complexity: Low (Phase 2 `CanvasSDKConfig` dataclass addresses this)

## Test Coverage Gaps

**SDK core modules:**
- What's not tested: `canvas_sdk/canvas.py`, `requester.py`, `paginated_list.py`, `canvas_object.py`, `config.py`
- Risk: Refactoring could break SDK without detection
- Priority: High (Phase 4 addresses this)
- Difficulty to test: Need mock HTTP responses and token validation

**TUI integration without Canvas:**
- What's not tested: Full TUI screen flow with mocked data
- Risk: Screen changes could break without detection
- Priority: Medium
- Difficulty to test: Requires Textual test infrastructure (not currently in CI)

---

*Concerns audit: 2026-05-05*
*Update as issues are fixed or new ones discovered*