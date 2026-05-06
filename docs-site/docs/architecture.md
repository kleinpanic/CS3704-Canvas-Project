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

## Security Architecture

### Browser demo: no tokens in client JS

The live demo at `kleinpanic.github.io/CS3704-Canvas-Project/demo/` calls the
fine-tuned Gemma4 v7-dpo model on a private HuggingFace Space. To do this
without exposing the HF token to the public:

```
Browser  ----POST /chat---->  Cloudflare Worker  ----Bearer HF_TOKEN---->  HF Space
                                  ^
                                  |
                              HF_TOKEN held as a Cloudflare secret
                              (set via `wrangler secret put HF_TOKEN`)
                              never reaches the browser, never in code
```

The Worker source lives at [`proxy/worker.js`](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/proxy/worker.js).
Deploy procedure and rotation steps: [`proxy/README.md`](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/proxy/README.md).

### Why this exists

An earlier build pipeline (pre-v3.0) injected secrets into a deployed JS file
via `sed` substitution at GitHub-Pages-deploy time. Because the secret never
entered the git index, gitleaks could not detect the leak — but `curl` against
the deployed site exposed the tokens in plaintext. Both leaked tokens were
rotated; the build-time injection was removed; the Worker pattern took its
place. The release checklist now requires a deployed-site grep verification
step before any release announcement.

### Properties of this design

- HF_TOKEN never reaches the browser; cannot be extracted from public JS.
- CORS whitelist restricts which origins may use the proxy.
- Body length cap (4000 chars) blocks trivial abuse.
- Free-tier Cloudflare (100k req/day, 10ms CPU per request) handles class
  demo load comfortably; the heavy lifting is on the HF Space.
- Rotation is one command (`wrangler secret put HF_TOKEN`), no code change
  and no redeploy.

### Zero-infra alternative

If the Worker is not deployed, [`proxy/iframe-fallback.html`](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/proxy/iframe-fallback.html)
embeds the HF Space directly in an iframe. Still no tokens anywhere, but
loses the polished chat UI.

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
