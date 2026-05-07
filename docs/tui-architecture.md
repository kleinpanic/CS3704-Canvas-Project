# TUI Architecture

Introduced in Phase 8 to document the screen-based TUI architecture, keybinding system,
and Chrome extension SDK contract.

---

## Overview

`canvas-tui` is a [Textual](https://textual.textualize.io/)-based terminal UI. As of Phase 8,
the application is decomposed into a thin App router (`src/canvas_tui/app.py`) and a set of
focused screen modules under `src/canvas_tui/screens/`. The `CanvasTUI` App pushes `HomeScreen`
on mount; all state (API client, config, cache, items) lives on `HomeScreen` so child screens
receive it via the `owner_app` parameter.

---

## Screen Inventory

| Screen | File | Purpose | Keybinding to reach |
|--------|------|---------|---------------------|
| HomeScreen | screens/home.py | Main assignment list, stats, charts, sidebar | (root screen) |
| DashboardScreen | screens/dashboard.py | Overview dashboard with scores and trends | `D` |
| GradesScreen | screens/grades.py | Per-course grade breakdown | `G` |
| WeekViewScreen | screens/weekview.py | 7-day calendar grid view | `W` |
| AnalyticsScreen | screens/analytics.py | Full Rich chart analytics | `V` |
| AnnouncementsScreen | screens/announcements.py | Course announcements list | `A` |
| CourseManagerScreen | screens/courses.py | Show/hide courses, course overview | `M` |
| FileManagerScreen | screens/files.py | Browse and download course files | `F` |
| SyllabiScreen | screens/syllabi.py | Syllabus viewer with preview pane | `S` |
| DetailsScreen | screens/details.py | Full detail view for a selected item | `Enter` |
| SettingsScreen | screens/settings.py | Theme, layout, keybinding preferences | `E` |
| HelpScreen | screens/help.py | Keybinding reference overlay | `?` |
| RMPScreen | screens/rmp.py | Rate My Professors search → results → details | `R` |
| CourseOverviewScreen | screens/course_overview.py | Per-course scores, weights, timeline | (from GradesScreen) |

---

## Keybinding Registry

`src/canvas_tui/keybindings.py` holds the module-level `REGISTRY` singleton.

```python
from canvas_tui.keybindings import REGISTRY

REGISTRY.register(screen="home", key="q", action="quit", help="Quit")
```

**API:**

- `Registry.register(screen, key, action, help)` — registers a binding; raises `ValueError` immediately
  if `(screen, key)` is already registered with a different action (D-05 conflict detection).
- `Registry.get_bindings(screen)` — returns `list[tuple[str, str, str]]` of `(key, action, help)`.
- `Registry.get_help(screen)` — returns a formatted plain-text table string for display in the `?` overlay.
- `Registry.validate_all()` — full scan for conflicts; called once at `CanvasTUI.__init__`. Exits with
  `sys.exit(1)` if any conflict is found, preventing silent keybinding misbehavior.

**Conflict detection:** registering the same `(screen, key)` pair with two different actions raises
`ValueError` at registration time. Re-registering with the *same* action is a no-op (idempotent).

**`?` overlay:** `BaseScreen.show_help_overlay()` pushes a `_HelpOverlay` modal that queries
`REGISTRY.get_help(self.screen_name)` to display a screen-specific keybinding table.

---

## BaseScreen ABC

`src/canvas_tui/screens/base.py` provides `BaseScreen(Screen)` — a thin subclass of Textual's `Screen`
with one added method: `show_help_overlay()`. Concrete screens set the `screen_name: str` class attribute
so the Registry knows which binding set to display.

Existing screens (DashboardScreen, GradesScreen, etc.) do not need to inherit from BaseScreen to work;
BaseScreen is the foundation for future screens that want the overlay without extra plumbing.

---

## Extension SDK Contract

The Chrome extension routes Canvas API calls through a native messaging host when it is installed,
with automatic fallback to direct browser-fetch if the host is unavailable.

### Request flow

```
Popup → background.js → routeViaHost(method, params, clientFallback)
                              │
                    ┌─────────┴─────────┐
                    │ host available?   │
                    │ yes               │ no
                    ▼                   ▼
         nativeCall(method, ...)   clientFallback()
                    │
         Python host (__main__.py)
                    │
         canvas_sdk.CanvasClient
```

### Host-routable MESSAGE_TYPES (14)

These MESSAGE_TYPES are tried via native host first, then fall back to browser fetch:

`getUpcoming`, `getCourses`, `getCourseAssignments`, `getCourseAnnouncements`,
`getCourseModules`, `getCourseGrades`, `getCourseFiles`, `getTodo`, `getPlannerNotes`,
`validateToken`, `getDashboardCards`, `getSyllabus`, `getAssignmentGroups`, `getSubmission`

### Browser-only MESSAGE_TYPES (stay on direct path)

`getToken`, `setToken`, `dismiss`, `clearCache`, `refreshBadge`, `getRmpRating`, `agentQuery`
These use Chrome APIs, IndexedDB, or extension-local state — they cannot route through the Python host.

### Adding a new host method

1. Add a new `if method == "myNewMethod":` block in `src/sdk/canvas_sdk/host/__main__.py`'s `_handle()` function.
2. Add the MESSAGE_TYPE to `extension/src/lib/extension-contract.js`.
3. Add a handler in `extension/src/background.js` using `routeViaHost('myNewMethod', params, fallback)`.

---

## RMP Integration

Data layer: `src/canvas_tui/rmp/` — `RMPClient`, `ProfessorRating`, `MatchResult`, matcher utilities.

TUI screen: `src/canvas_tui/screens/rmp.py` — `RMPScreen` with three states:
1. **search** — `Input` widget accepts professor name
2. **results** — `DataTable` shows matched professors with rating/difficulty columns
3. **details** — `Static` panel shows full `ProfessorRating` display properties

Keybinding: `R` from `HomeScreen` → `action_open_rmp()` → `push_screen(RMPScreen())`.
`RMPClient` is injectable via constructor for test isolation.
