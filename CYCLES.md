# Canvas TUI — Cycle Improvement Log

## Cycle 1

### Audit Findings

**Hat 1 — End User:**
- No "nothing selected" feedback when pressing action keys with empty table
- Quick preview (d) doesn't show notes/annotations
- No way to sort the table by different columns
- Ctrl+C bound to calcurse import — confusing, overrides default quit

**Hat 2 — UI/UX:**
- CANVAS_LOGO takes 8 lines of vertical space — too much on small terminals
- Progress bar and pomodoro in left panel have no visual separation
- Table "Rel" column shows relative time but never updates live
- No visual distinction for announcements vs assignments in the main table
- Type column wastes space with full words — could use icons/abbreviations

**Hat 3 — Developer:**
- `_pts_cell()` makes synchronous API calls during table render — blocks UI thread
- `_visible_items()` recomputes on every call — no memoization
- `_pending` dict uses `_modal_id` monkey-patching — fragile
- Many `assert self.table is not None` — should use proper null checks
- `on_screen_dismissed` is a mega-method with many elif branches

**Hat 4 — QA:**
- No test for normalize.py (0% coverage on core logic)
- No test for notifications.py
- No test for theme.py
- Missing edge case: what if course_cache is empty during normalize?

**Hat 5 — Packager:**
- requirements.txt still lists old deps — not synced with pyproject.toml
- No MANIFEST.in for sdist
- Old canvas-tui.py still in repo root (dead code)

**Hat 6 — Documentation:**
- No CHANGELOG.md
- Help screen doesn't mention G (grades), F (files), W (week view)
- No man page or --help long description

**Hat 7 — Security:**
- `_async_gather_attachments` parses HTML with regex — XSS via crafted href
- Token printed nowhere (good) but also no redaction in debug mode

**Hat 8 — Performance:**
- `_pts_cell()` sync fetch during render is the biggest perf issue
- `_stats()` iterates all items 4 times (4 separate comprehensions)
- `_render_table()` rebuilds entire table on every call

### Approved Proposals (Cycle 1)

1. **HIGH** — Fix _pts_cell sync API calls: move submission prefetch to refresh_data
2. **HIGH** — Add normalize.py tests (core logic, 0% coverage)
3. **HIGH** — Update help screen with all current keybindings
4. **HIGH** — Remove dead canvas-tui.py from repo root
5. **HIGH** — Sync requirements.txt with pyproject.toml
6. **MED** — Add CHANGELOG.md
7. **MED** — Add type abbreviations/icons in table (📝 assignment, 📋 quiz, etc.)
8. **MED** — Consolidate _stats() into single pass
9. **MED** — Fix Ctrl+C binding conflict
10. **LOW** — Add MANIFEST.in
