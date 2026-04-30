# Architecture

This project now has two active product surfaces:
- a Python/Textual TUI
- a browser extension with its own shared JS client/runtime layer

## Design Principles

- **Offline-first** where practical, using persistent cache layers
- **Shared contracts** instead of scattered UI-to-service coupling
- **Platform-specific adapters** for storage, notifications, and runtime details
- **Governed delivery** through CI/CD and protected `main`

## High-Level Layout

```text
TUI (Python)
  -> src/canvas_tui/
  -> Canvas API + SQLite-backed local state

Extension (JS)
  -> extension/src/popup/
  -> extension/src/background.js
  -> extension/src/lib/canvas-client.js
  -> extension/src/lib/cache.js
  -> Canvas API + IndexedDB-backed local state
```

## TUI Architecture

| Layer | Components | Files |
|-------|------------|-------|
| **Application** | App orchestration, routing, screens | `app.py`, `cli.py`, `screens/`, `widgets/` |
| **Domain/Data** | API, models, state, caching | `api.py`, `models.py`, `state.py`, `cache.py` |
| **Infrastructure** | Config, sync helpers, adapters | `config.py`, `prefetch.py`, `adapters/` |

## Browser Extension Architecture

The extension is no longer just an aspirational diagram. It now has a real layered structure.

| Layer | Role | Files |
|------|------|------|
| **UI** | Popup rendering and interaction | `extension/src/popup/*` |
| **Runtime bridge** | Message helpers and shared contract | `extension/src/lib/extension-api.js`, `extension/src/lib/extension-contract.js` |
| **Service orchestration** | Background handlers, badge updates, notifications | `extension/src/background.js` |
| **Canvas access** | Shared browser-side client methods | `extension/src/lib/canvas-client.js` |
| **Persistence** | IndexedDB stale-while-revalidate cache | `extension/src/lib/cache.js` |

## Why the Extension Refactor Matters

Recent work moved the extension away from:
- raw endpoint strings spread across multiple files
- popup code depending on raw Chrome runtime message names
- background logic acting as both transport and domain layer

The new structure centralizes:
- Canvas auth and endpoint access in `canvas-client.js`
- runtime message names in `extension-contract.js`
- popup/background calls in `extension-api.js`

That makes the extension easier to reason about and safer to extend.

## Cache Strategy

| Surface | Cache |
|---------|-------|
| **TUI** | SQLite / local Python-side persistence |
| **Extension** | IndexedDB with stale-while-revalidate helpers |

The two surfaces do **not** share a runtime cache implementation today, but they follow similar separation principles.

## Documentation Assets

### Static diagrams
- [Full Architecture SVG](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/docs/architecture/complex-architecture.svg)
- [Sync Flow SVG](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/docs/architecture/sync-flow.svg)

### Source diagrams
- `docs/architecture/complex-architecture.mmd`
- `docs/architecture/sync-sequence.mmd`

## Current Reality vs Future Goal

### Current reality
- strong TUI codebase
- working extension foundation
- shared browser-side client layer
- repo governance cleaned up around `main`

### Future goal
- deeper shared-core parity where business logic can be reused more directly across surfaces
- stronger tests around the extension runtime bridge and client methods
- broader extension feature coverage for files, announcements, and richer Canvas context
