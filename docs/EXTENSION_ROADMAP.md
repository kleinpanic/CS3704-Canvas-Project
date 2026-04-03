# Extension Roadmap

This document outlines the plan for browser extension parity and GUI upgrades.

## Vision

The Canvas TUI's **Shared Domain Core** enables feature parity between:
- Current: Textual TUI (terminal interface)
- Future: Browser Extension (Chrome/Firefox)
- Future: Desktop GUI (optional)

## Phase 1: Core Abstraction (PM4)

**Goal**: Extract reusable domain logic

### Tasks
- [ ] Define `CanvasClient` abstract interface
- [ ] Create `AuthManager` protocol (keyring vs OAuth)
- [ ] Implement `CacheBackend` abstraction (SQLite vs IndexedDB adapter)
- [ ] Design `NotificationCenter` interface
- [ ] Document domain boundaries

### Deliverables
- `src/canvas_tui/core/` — shared domain layer
- `src/canvas_tui/adapters/` — platform adapters
- Architecture decision records (ADRs)

## Phase 2: Browser Extension (PM5)

**Goal**: Chrome/Firefox extension with same features

### Architecture
```
┌─────────────────────┐
│  Browser Extension   │
│  ┌─────────────────┐ │
│  │ Popup UI        │ │
│  │ Background      │ │
│  │ Content Scripts │ │
│  └────────┬────────┘ │
└───────────┼──────────┘
            │
┌───────────▼──────────┐
│   Shared Domain Core  │
│  (same business logic)│
└───────────┬──────────┘
            │
┌───────────▼──────────┐
│  Platform Adapters    │
│  - OAuth2 flow        │
│  - IndexedDB cache    │
│  - Browser notifs     │
└──────────────────────┘
```

### Tasks
- [ ] Create extension manifest (MV3)
- [ ] Implement OAuth2 flow
- [ ] Build IndexedDB cache adapter
- [ ] Design popup UI (React/Vue)
- [ ] Wire background service worker
- [ ] Cross-browser testing

### Deliverables
- `extension/` — browser extension source
- Build scripts for Chrome/Firefox
- Extension-specific tests

## Phase 3: Desktop GUI (Future)

**Goal**: Native desktop app with modern UI

### Options
1. **PyWebView** — HTML/CSS/JS UI with Python backend
2. **PyQt/PySide** — Native Qt widgets
3. **Electron** — Full JS stack (separate from Python core)
4. **Tauri** — Rust backend, web frontend

### Recommendation
**PyWebView** — reuses existing architecture, Python backend, HTML/CSS frontend.

### Tasks (Future)
- [ ] Evaluate PyWebView integration
- [ ] Design responsive UI mockups
- [ ] Implement native notification bridge
- [ ] Platform-specific packaging

## Feature Parity Matrix

| Feature | TUI | Extension | Desktop |
|---------|-----|-----------|---------|
| Dashboard | ✓ | Planned | Planned |
| Assignments | ✓ | Planned | Planned |
| Grades | ✓ | Planned | Planned |
| Announcements | ✓ | Planned | Planned |
| Files | ✓ | Planned | Planned |
| Calendar | ✓ | Planned | Planned |
| Offline Cache | ✓ (SQLite) | Planned (IndexedDB) | Planned |
| Notifications | ✓ (terminal) | ✓ (browser) | ✓ (native) |
| Pomodoro | ✓ | ✓ | ✓ |

## Architecture Decisions

### ADR-001: Shared Domain Core
**Status**: Proposed

Separate business logic from UI/platform code. This enables:
- Feature parity without duplication
- Shared test coverage for core logic
- Platform-specific optimizations

### ADR-002: OAuth2 for Extension
**Status**: Proposed

Use Canvas OAuth2 for browser extension (not API tokens):
- Better security (no token storage)
- Institutional login flow
- Automatic token refresh

### ADR-003: IndexedDB Cache
**Status**: Proposed

Use IndexedDB for browser extension caching:
- Larger storage quota than localStorage
- Async API matches extension patterns
- Supports complex queries

## Timeline

| Milestone | Target | Scope |
|-----------|--------|-------|
| PM4 | Apr 2026 | Core abstraction |
| PM5 | May 2026 | Browser extension MVP |
| PM6 | Jun 2026 | Extension polish + testing |
| Post-course | 2026+ | Desktop GUI exploration |

## Resources

- [Chrome Extension Docs](https://developer.chrome.com/docs/extensions/)
- [IndexedDB API](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API)
- [Canvas OAuth2](https://canvas.instructure.com/doc/api/file.oauth.html)
- [PyWebView](https://pywebview.io/)

## Next Steps

1. Review and approve this roadmap
2. Create issues for PM4 abstraction tasks
3. Begin domain layer extraction
4. Draft extension manifest

---

**Owner**: @kleinpanic
**Last Updated**: 2026-04-03
