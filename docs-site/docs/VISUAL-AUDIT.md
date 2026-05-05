# CS3704 Canvas TUI — Visual Audit + Advancement Plan

## Visual Audit

### Current Problems

The TUI is **functional but visually crowded**. Every panel is competing for attention with no breathing room or hierarchy.

**Specific issues by screen:**

#### Dashboard (most broken)
- 5 panels rendered simultaneously: logo, scores, due soon, completion, trends
- No borders or containers around any panel — all just plain text in Vertical/Horizontal containers
- Due-soon list shows up to 12 items with no visual separation between them
- "Course Scores" bar chart squished into a narrow panel that doesn't have room to breathe
- Trends sparkline text label is too long and wraps weirdly
- No padding between urgency tags and item text
- OVERDUE items get a hard `[red]OVERDUE[/red]` tag that breaks the flow

#### Main screen (app.py)
- `#stats-row` with 4 `.stat-cell` columns showing filter summary, download status, cache stats, sync info — all crammed into 4-7 lines max
- `#chart-area` showing grade charts but with no label headers — you have to infer what the charts are from the data
- `#sidebar` doing too much: side-info + side-details + pomodoro + side-charts all at once
- The DataTable itself is fine but the supporting panels around it are cluttered

#### Grades screen
- `grades-summary` Static trying to show avg + projected_avg + what-if inputs all in one line
- Course table and grade table are both zebra-striped DataTables — no visual distinction between which is which
- The "what-if" calculator is completely invisible unless you know it exists

#### Week View
- 7-day Grid with `.day-cell` border using solid `#30363d` — the borders ARE there which is good
- Each day shows items without type icons (ASGN/QUIZ/DISC tags) — just raw text
- Items capped at 8 per day but no "and N more" indicator
- Day header (Mon 04/14) + today marker (◄) is fine

#### Command bar + status bar
- `#cmd-bar` at bottom only shows keybinds — useful but no contextual hint about current screen
- `#status-bar` only shows cache status — no current filter, no course context, no help text

### What Actually Looks Good

- **Color scheme**: GitHub dark theme (`#161b22` bg, `#30363d` borders, `#8b949e` text) — cohesive
- **Font choices**: Monospace and bold weights used appropriately
- **Grades screen**: The split layout (course list | detail + grades table) works well
- **Week view grid**: 7-day layout is clean and readable
- **Urgency colors**: Red/yellow/green/cyan urgency system is clear and useful

### Visual Fixes to Make

1. **Dashboard panels need border containers** — use `border: solid #30363d` + `padding: 1 2` to visually group each section
2. **Dashboard needs a clear visual hierarchy** — right now logo + scores + due + completion + trends are all equal weight; pick one primary focus
3. **Due-soon items need type indicators** — "ASGN", "QUIZ", "DISC" tags before each item like the week view has
4. **Remove `[red]OVERDUE[/red]` tag and replace with inline colored badge** — `● OVERDUE` style inline
5. **Add panel headers** to all dashboard panels (e.g., "── Due Soon ──" or box-style headers)
6. **Course completion gauges are too wide** — they overflow in narrow terminals
7. **Stats row should be collapsible** or reduced to a single-line summary

---

## Advancement Plan

### Phase 1: Visual Polish (1-2 weeks)
- Fix dashboard panel layout: borders, headers, spacing, type icons
- Add a `?` help hint in the status bar that adapts to current screen
- Make "what-if" calculator discoverable in Grades screen (add a hint or toggle)

### Phase 2: Core Architecture Refactor for Web Extension (2-4 weeks)

The TUI works but the code is tightly coupled. To build a web extension, we need a proper abstraction layer.

#### 2.1 Extract `core/` directory
```
src/canvas_tui/
├── core/
│   ├── __init__.py
│   ├── client.py       # CanvasClient abstract interface
│   ├── cache.py        # CacheBackend protocol + SQLite implementation
│   ├── auth.py         # AuthManager protocol + env-var implementation
│   └── models.py      # Domain models (CanvasItem, Course, etc.) — extracted from models.py
```

#### 2.2 Define interfaces
```python
class CanvasClient(Protocol):
    def fetch_courses(self) -> dict[int, tuple[str, str]]: ...
    def fetch_announcements(self, course_id: int) -> list[dict]: ...
    def fetch_grades(self, course_id: int) -> list[dict]: ...
    # etc.

class CacheBackend(Protocol):
    def get(self, key: str, allow_stale: bool = False) -> tuple[dict | None, bool]: ...
    def put(self, key: str, data: dict, ttl: int | None = None) -> None: ...
    def invalidate(self, key: str) -> None: ...
    def stats(self) -> dict: ...
```

#### 2.3 Replace direct imports
- `screens/` and `widgets/` currently import from `api.py` and `cache.py` directly
- Change to import from `core.client` and `core.cache` via the interfaces
- The TUI keeps working the same way — but now `client.py` wraps `api.py` and `cache.py` wraps SQLite

#### 2.4 Add browser extension scaffolding
```
browser-extension/
├── manifest.json      # Chrome/Firefox extension manifest v3
├── src/
│   ├── background.js  # Service worker, Canvas API calls via same client.py
│   ├── popup/         # Extension popup UI
│   └── content/       # Content script for in-page Canvas integration
├── assets/            # Icons
└── tests/             # Extension integration tests
```

**The key insight**: `core/client.py` with the `CanvasClient` protocol is the shared contract. The TUI calls it via Python, the browser extension calls the same interface via JavaScript. The business logic is identical — only the transport layer differs.

### Phase 3: Web Extension MVP (4-8 weeks)
- Popup showing upcoming deadlines, synced via same Canvas API
- Option to use the Python TUI's cache as a backend (via HTTP server exposing the cache)
- Browser notification on deadline approach
- Integration with Canvas page via content script

### Phase 4: Deployment + Distribution
- `make build` already works (`python -m build` → `dist/`)
- Add a proper `setup.py` entry point for `pip install canvas-tui`
- PyPI upload for easy `pip install canvas-tui` installation
- Browser extension to Chrome Web Store / Firefox Add-ons

---

## Dependency: What Must Come First

The visual polish (Phase 1) can start immediately — it doesn't break anything.

The core architecture refactor (Phase 2) is a prerequisite for everything else. Without it:
- A web extension would require duplicating all the business logic in JavaScript
- The TUI would be harder to maintain as two codebases diverged

**Start with Phase 1 (visual polish) while planning Phase 2.** Phase 2 is a 2-4 week refactor that should be done carefully and tested thoroughly before moving to Phase 3.

---

## Quick Wins (do now, low effort, high impact)

1. **Add type badges to dashboard due-soon items** — 30 min work, instant visual improvement
2. **Add border containers to dashboard panels** — 1 hr work, clears up the clutter
3. **Add "press ? for help" to status bar** — 30 min work, improves discoverability
4. **Fix OVERDUE tag inline styling** — 15 min work, cleaner text rendering
5. **Add course code header to grades table** — 15 min work, context awareness

These 5 changes would significantly improve the visual experience without touching any logic.