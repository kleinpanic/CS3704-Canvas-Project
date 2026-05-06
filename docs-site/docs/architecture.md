# Architecture

The project has four components:

- **canvas_sdk** (`src/sdk/canvas_sdk/`) — Python library wrapping the Canvas REST API. Typed resource classes, a paginated request layer, and an agent tool registry used by the HF Space demo.
- **canvas_tui** (`src/canvas_tui/`) — Python/Textual terminal UI that consumes `canvas_sdk` directly.
- **extension** (`extension/`) — Chrome MV3 browser extension. Calls Canvas via `canvas-client.js`; optionally bridges to a local SDK host process through native messaging.
- **proxy** (`proxy/`) — Cloudflare Worker that stands between the live demo page and the HF Space, keeping the HF token out of public JS.

## Data Flow

```text
canvas_tui  ──────────────────────────────────>  Canvas API
   (via canvas_sdk)

extension  ──── canvas-client.js ─────────────>  Canvas API
   (IndexedDB cache)
   └── native messaging ──────────────────────>  canvas_sdk host process

browser demo  ──POST /chat──>  Cloudflare Worker  ──Bearer HF_TOKEN──>  HF Space
```

The Cloudflare Worker only proxies demo chat traffic. It is not involved in Canvas API access.

## canvas_sdk

`src/sdk/canvas_sdk/` is a standalone Python package. The `Canvas` class in `canvas.py` is the entry point. The `agent_tools/` subpackage provides a tool registry (`REGISTRY`, `get_schemas()`, `dispatch()`) in Ollama/Gemma function-calling format, used by the HF Space agent.

## canvas_tui

`src/canvas_tui/` is the terminal application built on Textual.

| Layer | Files |
|-------|-------|
| App shell | `app.py`, `cli.py` |
| Screens | `screens/` (dashboard, grades, files, syllabi, announcements, analytics, week view, settings) |
| Widgets | `widgets/` (command bar, pomodoro, plots) |
| Data | `api.py`, `models.py`, `state.py`, `cache.py`, `normalize.py`, `filtering.py` |
| Infrastructure | `config.py`, `prefetch.py`, `adapters/` (SQLite cache backend) |

Canvas responses are cached in SQLite through `CacheBackendAdapter`.

## Browser Extension

`canvas-client.js` owns all Canvas API calls and authentication. `extension-contract.js` defines message names shared between popup and background. `extension-api.js` wraps those so popup code never depends on raw runtime message strings. `background.js` handles service worker lifecycle, badge updates, and notification dispatch. `cache.js` implements a stale-while-revalidate store in IndexedDB.

The manifest declares `nativeMessaging` permission. `native-host.js` manages a persistent connection to `com.cs3704.canvas_tracker`, letting the extension delegate Canvas queries to the Python SDK host process when running locally.

## Cloudflare Worker Proxy

The live demo calls a fine-tuned Gemma model on a private HF Space. The Worker (`proxy/worker.js`) receives `POST /chat` from the browser and forwards it with a bearer token stored as a Cloudflare secret. The token never reaches the browser.

```text
Browser  ──POST /chat──>  Cloudflare Worker  ──Bearer HF_TOKEN──>  HF Space
                              ^
                          HF_TOKEN set via: wrangler secret put HF_TOKEN
```

An earlier build pipeline injected secrets into deployed JS via `sed` at deploy time. Because the secret never entered the git index, gitleaks could not detect the leak, but `curl` against the live site exposed the token in plaintext. Both leaked tokens were rotated, the build-time injection was removed, and the Worker pattern replaced it. The release checklist now includes a deployed-site grep verification step.

CORS is restricted to an origin whitelist. Request bodies are capped at 4000 characters. Rotating the token requires one command and no redeploy: `wrangler secret put HF_TOKEN`.

If the Worker is not deployed, [`proxy/iframe-fallback.html`](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/proxy/iframe-fallback.html) embeds the HF Space in an iframe — no tokens anywhere, but loses the chat UI.

## Documentation Assets

- [Full Architecture SVG](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/docs/architecture/complex-architecture.svg)
- [Sync Flow SVG](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/docs/architecture/sync-flow.svg)
- Source: `docs/architecture/complex-architecture.mmd`, `docs/architecture/sync-sequence.mmd`
