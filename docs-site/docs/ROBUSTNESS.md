# Robustness Guide

This document covers the testing strategy, CI gates, error-handling conventions, and overall reliability posture of the project.

---

## Test Suite

Tests live in `tests/` and are run via `pytest`.

```bash
pytest tests/ -v
```

### Test Structure

| Module | Coverage |
|--------|----------|
| `test_api.py` | Canvas API client and HTTP layer |
| `test_cli.py` | CLI argument parsing and entry point |
| `test_config.py` | Settings persistence, keybindings, theme/layout |
| `test_courses.py` | Course data normalization |
| `test_deadline.py` | Deadline detection and notification scheduling |
| `test_filtering.py` | Assignment/event filtering logic |
| `test_grades.py` | Grade normalization and display |
| `test_ics.py` | ICS calendar export |
| `test_models.py` | Pydantic/data model validation |
| `test_notifications.py` | Notification formatting and dispatch |
| `test_plots.py` | Chart/plot rendering |
| `test_reranker.py` | GemmaReranker scoring |
| `test_state.py` | App state transitions and persistence |
| `test_theme.py` | Theme application |
| `test_utils.py` | General utility functions |
| `rmp/` | RateMyProfessor matching (separate integration) |

### Running Specific Tests

```bash
# Single module
pytest tests/test_api.py -v

# By keyword
pytest -k "config" -v

# With coverage
pytest tests/ --cov=src/canvas_tui --cov-report=term-missing
```

---

## CI/CD Gates

All PRs run through the full CI matrix before merge. See `.github/workflows/` for the canonical definitions.

### Required Checks

1. **Branch name policy** — enforced via `super-linter` or equivalent
2. **Python compatibility** — tested on 3.11, 3.12, 3.13
3. **Test suite** — must pass on all supported Python versions
4. **Type checking** — if `pyright` or `mypy` is configured, must be clean

### Release Workflow

The release workflow runs `require-ci` as a polling job (~2–3 minutes). It is triggered by version tags matching `v*.*.*`.

```bash
# Always tag with the v prefix
git tag v1.2.3 && git push origin v1.2.3
```

See [release-checklist.md](release-checklist.md) for the full step-by-step release procedure.

---

## Error Handling

### API Layer (`src/canvas_tui/api.py`)

- Network errors are caught and re-raised as typed `CanvasError` exceptions
- HTTP 4xx responses are treated as client errors (non-retryable)
- HTTP 5xx responses trigger exponential backoff retry (up to 3 attempts)
- All API calls log at `DEBUG` level with method + endpoint on entry

### Cache Layer (`src/canvas_tui/cache.py`)

- Cache misses fall back gracefully to live API calls
- Corrupt cache entries are logged and purged; they do not crash the app
- TTL expiry is enforced on read, not write (writes always succeed)

### Config Layer (`src/canvas_tui/config.py`)

- Missing config keys use safe defaults rather than crashing
- Schema validation errors are surfaced clearly before the app starts
- Sensitive fields (tokens) are never written to logs

---

## Offline-First Behavior

The app is designed to work offline with a warm cache:

1. On first launch, seed the cache from Canvas API responses
2. On subsequent launches, serve from cache immediately and refresh in background
3. If API is unreachable, fall back to cache and show a stale-data indicator

---

## Cross-AI Review

All non-trivial PRs go through a formal cross-AI review process documented in `REVIEWS.md` at the repo root. Key points:

- Reviewers run the full test suite and report findings before merge
- Gemini review findings must be addressed before the PR is merged
- Critical findings (crashes, data loss, auth bypass) block merge entirely

---

## Dependency Management

- All runtime dependencies are pinned with lower bounds in `pyproject.toml`
- The `.venv` is regenerated from `pyproject.toml` on CI; no `requirements.txt` drift
- New dependencies require a test pass and a human review step

---

## Monitoring & Alerts

| Signal | How it's handled |
|--------|-----------------|
| Test failures on PR | CI blocks merge |
| Release workflow failure | GitHub Actions alerts repo owner |
| Stale PR (>14 days) | `stale.yml` workflow applies close label |
| Cache corruption | Logged and purged; app continues with live API |