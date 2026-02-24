# Canvas TUI Graphics Overhaul — Autonomous Work Plan

Task: `8e2fb12b-2872-4188-89e1-052b2f51c9d3`
Repo: `~/codeWS/Python/CanvasTui-Proposal`

## Phase 1: Fix Broken Charts (Issues #2, #3, #9, #11)

### 1.1 Fix scatter plot invisible data (Issue #2)
- In `charts.py:scatter_scores()` — change `marker="braille"` to `marker="dot"` or `marker="hd"` for visibility
- Add `plt.ylim(0, 100)` bounds

### 1.2 Fix histogram negative bins (Issue #3)
- In `charts.py:grade_histogram()` — clamp scores to `[0, 100]` before passing to `plt.hist()`
- Set explicit `plt.xlim(0, 100)`

### 1.3 Fix submission heatmap logic (Issue #9)
- In `analytics.py:_build_submission_heatmap()` — the filter is INVERTED:
  - Current: `if "submitted" not in it.status_flags: continue` — this SKIPS submitted items!
  - Fix: `if "submitted" in it.status_flags:` should be the condition to INCLUDE items
  - Also: use submission timestamp if available, not just `due_iso`

### 1.4 Normalize course code labels (Issue #11)
- Centralize truncation to a helper: `_course_label(code: str, max_len: int = 12) -> str`
- Strip trailing underscores
- Use consistently in analytics.py (currently `[:10]`) and app.py (currently `[:12]`)

## Phase 2: Eliminate plotext Dependency (Issues #1, #5, #8)

### 2.1 Rewrite `charts.py` using Rich-native rendering
Replace every plotext function with Rich markup equivalents:
- `score_bar_chart()` → Rich horizontal bars (like `plots.py:render_bar_chart()` but with axes)
- `grade_histogram()` → Rich vertical bar chart with half-block characters
- `multi_line_chart()` → Rich braille overlay plot (fix `plots.py` first, Issue #12)
- `scatter_scores()` → Rich braille scatter
- `submission_heatmap()` → Rich Table with background-colored cells
- `completion_bullet()` → Rich horizontal bars with target markers
- `weekly_activity_chart()` → Rich vertical bars

### 2.2 Fix braille plot overlay (Issue #12)
- Current: renders each series on separate grids stacked vertically
- Fix: overlay ALL series onto ONE shared grid, then render once
- Color: use first series' color for dots (or alternate per-value)

### 2.3 Remove plotext from dependencies
- Remove `plotext` from `pyproject.toml`
- Delete `import plotext` and `_to_rich` / `_setup` helpers

## Phase 3: Theme Integration (Issue #7)

### 3.1 Create chart color palette from theme
- Add `CHART_PALETTE` to `theme.py` — list of 8 colors derived from theme tokens
- Add `grade_colors()` method to `ThemeColors` that returns grade→color mapping
- Centralize grade_color / urgency_color into theme

### 3.2 Wire all chart functions through theme
- `plots.py`: use `get_theme().CHART_PALETTE` instead of hard-coded color lists
- `charts.py`: same
- `grades.py`: use theme tokens
- `dashboard.py`: use theme tokens
- `analytics.py`: use theme tokens
- `app.py`: use theme tokens for sidebar charts

## Phase 4: Responsive Sizing (Issue #4, #6)

### 4.1 Charts query container size
- Each chart function already accepts `width`/`height` params
- Fix callers in analytics.py and app.py to pass actual container sizes
- Use `self.query_one("#id").size` or `self.size` for real dimensions
- For braille plots: calculate from available characters

### 4.2 Analytics screen responsive grid
- Each chart pane should use Textual's `on_resize` to re-render at correct size
- Add `on_resize` handler to AnalyticsScreen that re-renders all charts

## Phase 5: Layout Polish (Issue #8, #10)

### 5.1 Remove plotext frame borders (Issue #8)
- After Phase 2, this is automatic — no more plotext border frames

### 5.2 Fix completion bullet chart (Issue #10)
- Pass actual target values (100% per course) so the bullet chart shows actual vs target
- Or redesign as a proper completion gauge per course

### 5.3 Styled empty states
- Replace bare `[dim]No data[/dim]` with centered, styled placeholders
- Collapse empty panes where possible

## Validation
- Run `make test` after each phase
- Launch app in tmux and visually inspect every chart
- Screenshot before/after for comparison
- Run `ruff check` for lint

## Execution Order
1. Phase 1 (quick fixes) → test
2. Phase 2 (the big rewrite) → test
3. Phase 3 (theme wiring) → test
4. Phase 4 (responsive) → test
5. Phase 5 (polish) → test
6. Final visual validation in tmux
