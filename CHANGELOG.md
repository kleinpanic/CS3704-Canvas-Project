# Changelog

All notable changes to Canvas TUI are documented here.

## [1.0.0] — 2026-02-23

### Added
- Complete rewrite from monolith to 24-module `src/canvas_tui/` package
- **Grades overview** with per-course breakdown, weighted averages, sparkline trends
- **File manager** with folder navigation, multi-select, batch downloads
- **Calendar week view** with 7-day grid and time-based placement
- **Structured filtering** with `course:` `type:` `status:` `has:` syntax + fuzzy search
- **Offline mode** with disk-backed response cache (15min TTL, stale-while-offline)
- **Dark/light themes** with toggle (`T` key)
- **CLI flags**: `--export-ics`, `--no-cache`, `--debug`, `--theme`, `--days-ahead`, `--past-hours`
- **Due date notifications** at 60/30/15 minutes before deadlines
- **Pomodoro timer** with title bar display, desktop notifications, bell
- **Keyring support** for secure token storage
- **Help screen** (`?`) with categorized keybindings and filter syntax reference
- **Comprehensive test suite** — 90+ tests across 8 modules
- **Dockerfile** for containerized deployment
- **GitHub Actions CI/CD** — lint, typecheck, test matrix, auto-release on tags
- ASCII Canvas logo in header

### Fixed
- Thread-safe state manager (race condition in saves)
- Proper HTML stripping via `html.parser` (replaces naive regex)
- N+1 course fetch eliminated (batch course cache)
- Temp file cleanup via `atexit`
- Config key inconsistency (`ann_futuredays` / `ann_future_days`)
- UUID-based modal tracking (replaces fragile `id(screen)`)
- Config validation with safe bounds checking
- Lambda closure bugs in error handlers

### Changed
- Typed `CanvasItem` dataclass replaces raw dicts throughout
- Responsive CSS layout with `fr`-based proportional sizing
- ICS export extracted to reusable `ics.py` module
- Rate-limit header parsing (`X-Rate-Limit-Remaining`)

## [0.5.0] — 2026-02-01

### Added
- Initial TUI with planner, announcements, syllabi
- Pomodoro timer
- ICS export
- Calcurse import
