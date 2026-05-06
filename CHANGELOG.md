# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] — 2026-05-04

### Added
- **SDK agent registry**: 18-tool agent registry with Canvas API tools (×8), calendar adapters (×5), study helpers (×4), and reranker integration (×1) — registered via `REGISTRY` dict with auto-discovery
- **Settings UI**: full config persistence, keybinding customization, and theme/layout settings screen
- **Multi-view extension navigation**: courses tab with drill-down navigation and per-tab content rendering in the browser extension popup
- **Canvas scraper**: full 4-year history, submission status tracking, `@COURSE` anonymization prefix, and bulk contribution converter
- **Rate My Professor integration**: standalone RMP module for instructor lookup
- **Trajectory data collection**: teammate contribution pipeline with privacy scrubber and anonymization

### Changed
- **Chart sizing**: responsive layout using viewport size instead of `content_size` for accurate pane sizing
- **TUI layout improvements**: tighter sidebar, balanced stats row widths, reduced completion bars
- **Extension architecture**: shared `canvas-client.js`, `extension-contract.js`, and `extension-api.js` layers replace scattered endpoint logic
- **Dataset pipeline**: standardized on 8 core commands (setup, generate, merge, clean, anonymize, export-sft, export-dpo, split)
- **Heuristic weights**: synchronized `W_TIME=3.0`, `W_TYPE=2.5`, `W_POINTS=1.5`, `W_STATUS=2.0` across all reranker scripts
- **CI simplified**: lint no longer blocks merges; coverage advisory at 80% with `#no-coverage-check` bypass
- **Python compatibility**: smoke test runs on 3.11/3.12/3.13 (informational, non-blocking)
- **Branch protection**: only Test, Coverage, Python Compat block merge; code owner reviews required

### Fixed
- **CRN anonymization**: regex now correctly handles underscore-delimited CRN format in course identifiers
- **Coverage threshold**: Textual TUI layer omitted so 80% threshold is actually achievable
- **Dead code**: four unused variables reintegrated after vulture analysis
- **Canvas scraper**: `share_my_canvas.py` works canvas-only, no API keys required
- **CI broken by cleanup**: `run_pipeline.py` restored to `scripts/`

### Docs
- `docs-site/` deployed site: architecture, extension, workflow, and roadmap pages updated
- `docs/project/DEVELOPER_GUIDE.md` — onboarding, setup, test/run/build commands
- `docs/contributing-data.md` — teammate data-contribution guide
- Zenodo DOI alongside HuggingFace in ML release notes
- Dead link to private training repo removed from README

### Dependencies
- `actions/github-script` v7→v9 (dependabot)
- `actions/download-artifact` v5→v8 (dependabot)
- Python SDK package added: `canvas_sdk` v1.0.0 in `sdk/` subdirectory

### Project Maintenance
- 241 tests passing
- 189 commits since v1.0.0
- All William Martin's PRs merged (extension nav, TUI fixes, settings UI, data stubs)
- Project board maintained at github.com/kleinpanic/projects/5

---

## [1.1.0] — 2026-04-15

### Added
- **DPO support in dataset pipeline**: `collect_rerank_dataset.py` now supports `export-dpo` for distillation workflows
- **Anonymization in SFT export**: added `--anonymize` flag to `export-sft` for safer data sharing
- **Deterministic benchmark tiebreaker**: `benchmark.py` updated to use heuristic scoring as a stable fallback instead of random choice
- **Version display** in TUI header (title bar shows `CanvasTUI v1.1.0`)
- **Type badges** in dashboard: ASGN / QUIZ / DISC / EXAM / EVNT inline labels
- **Box-drawing panel headers** with Unicode border characters
- **Inline urgency labels** on due items (e.g. "today", "tomorrow", "3d")
- **Grades what-if discoverability hint** on grades screen
- **`src/canvas_tui/models/` package**: `item.py`, `course.py`, `modal.py`, `__init__.py` (restructured from `models.py`)
- **Reranker fine-tuning pipeline** (Gemma 2B target):
  - `scripts/generate_rerank_data.py` — 20 query types, 5 pair types, multi-dim urgency scoring
  - `scripts/train_reranker.py` — LoRA fine-tuning with configurable rank/alpha/lr/dropout
  - `scripts/eval_reranker.py` — pairwise accuracy evaluation against ground truth
- **CI fixup workflow** (`ai-fixup.yml`) — auto-generates fix patches via Nemotron on DGX Spark on CI failure
- **Auto-docs workflow** (`auto-docs.yml`) — post-merge docstring generation via Nemotron

### Fixed
- Status bar: removed stale "Last refresh" and "Rate: ?" fields
- Prompt defense skill integration for school agent pipelines

### Changed
- **CI simplified**: lint no longer blocks merges; coverage advisory at 80% with `#no-coverage-check` bypass
- Python compatibility smoke test runs on 3.11/3.12/3.13 (informational, non-blocking)
- Branch protection: only Test, Coverage, Python Compat block merge

### Docs
- `docs/project/DEVELOPER_GUIDE.md` — onboarding, setup, test/run/build commands
- `docs-site/` deployed docs site updated

### Dependencies
- PRs merged: dependabot updates for `actions/github-script` v7→v9 (#22), `actions/download-artifact` v5→v8 (#21)

### Project Maintenance
- Issues closed: #15 (dashboard type badges), #24 (PM4 test_cache.py), #19, #18, #16 (Phase 2/3 future work)
- 241 tests passing

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
