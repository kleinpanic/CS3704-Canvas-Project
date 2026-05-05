# External Integrations

**Analysis Date:** 2026-05-05

## APIs & External Services

**Canvas LMS REST API:**
- Purpose: Fetch courses, assignments, grades, announcements, calendar events, submissions
- Integration method: REST API via `requests` library
- Auth: Bearer token (`CANVAS_TOKEN` env var) — passed as `Authorization: Bearer <token>` header
- Endpoints used: `/api/v1/` prefix (e.g., `/api/v1/courses`, `/api/v1/users/:id`)
- Rate limits: Canvas enforces `X-Rate-Limit-Remaining` header; both clients handle 429 responses
- Base URL: Configured via `CANVAS_BASE_URL` (e.g., `https://vt.instructure.com`)

**RateMyProfessors (RMP) API:**
- Purpose: Course/instructor ratings in TUI analytics screen
- Integration method: HTTP client in `src/canvas_tui/rmp/client.py`
- Auth: None (public API)
- Note: RMP has no official API; integration uses scrape patterns

## Data Storage

**Disk Cache:**
- Tool: SQLite via `src/canvas_tui/adapters/sqlite_cache.py` and `src/canvas_tui/cache.py`
- Purpose: Cache Canvas API responses for offline mode and rate-limit reduction
- Location: `~/.cache/canvas-tui/` or per-configured cache directory
- TTL: Configurable per installation

**SDK Cache:**
- Tool: `canvas_sdk/requester.py` uses `requests.Session` with internal `_cache` list (memory-only)

## Configuration

**Environment Variables (required for TUI + SDK):**
- `CANVAS_TOKEN` — Access token (no default, must be set)
- `CANVAS_BASE_URL` — Canvas instance root (e.g., `https://vt.instructure.com`)
- `TZ` — Timezone (defaults to `America/New_York`)
- `EXPORT_DIR` — Export output directory (defaults to current directory)

**Environment Variables (optional):**
- `KEYRING_SERVICE` — Use system keyring for token storage
- `RERANKER_MODEL_PATH` — Local GGUF model for reranking (AI extra)

## CI/CD & Deployment

**GitHub Actions:**
- Workflows: `.github/workflows/ci.yml` (pytest + coverage check)
- Python versions tested: 3.11 (ubuntu-latest)
- Secrets: None required (tests run against mock/real Canvas, no external deps)

---

*Integration audit: 2026-05-05*
*Update when adding/removing external services*