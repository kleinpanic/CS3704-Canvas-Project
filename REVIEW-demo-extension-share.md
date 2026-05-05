# Demo + Extension Code Sharing Audit

**Audit date:** 2026-05-05
**Branch:** audit/demo-extension-sharing
**Prior art:** REVIEW-extension-sdk.md (Phase 19, Task 3) — builds on findings #2 and #3 from that audit.

---

## Existing extension JS surface

| File:line | Function / export | What it does |
|---|---|---|
| `extension/src/lib/canvas-client.js:19` | `class CanvasClient` | Central HTTP client: baseUrl + auth header + per-endpoint methods (`getCourses`, `getCourseAssignments`, `getUpcomingAssignments`, `getCourseGrades`, `getDashboardCards`, `getCourseSyllabus`, `getAssignmentGroups`, `getSubmission`, `getCourseFiles`, `getCourseAnnouncements`, `getCourseModules`). **Only implementation of Canvas API auth in the JS tree.** |
| `extension/src/lib/canvas-client.js:52` | `CanvasClient.request()` | Centralized fetch with Bearer auth, 401 token-expiry handling, JSON/text auto-detect. No retry logic. |
| `extension/src/lib/reranker.js:34` | `RANK_PROMPT_TEMPLATE` + `getRankPromptFormatSha()` | Canonical prompt template shared with `src/canvas_tui/reranker.py`; SHA used as a drift guard. |
| `extension/src/lib/reranker.js:84` | `serializeItem(item)` | Serializes a Canvas item (type badge, anonymized course code, due label, points) into the format the reranker model was trained on. |
| `extension/src/lib/reranker.js:112` | `class OllamaReranker` | Direct Ollama HTTP client — flagged HIGH in REVIEW-extension-sdk.md finding #1. |
| `extension/src/background.js:124` | `runLocalAgent(query)` | Regex intent classifier (6 intents) + tool dispatch against `CanvasClient` + fallback to native host. Flagged HIGH in REVIEW-extension-sdk.md finding #2. **First copy of the agent loop.** |
| `extension/src/lib/extension-api.js:9` | `send(type, payload)` + all exported wrappers | Thin bridge from popup to background via `chrome.runtime.sendMessage`. Source of truth for the `MESSAGE_TYPES` → popup API surface. |
| `extension/src/lib/extension-contract.js:7` | `MESSAGE_TYPES` | Canonical message-type constants for the popup↔background contract. |
| `docs-site/chrome_shim_prod.js:50` | `AGENT_QUERY` handler | Reimplements `runLocalAgent` with a 3-intent regex classifier for GitHub Pages use — references `upcoming.json` static data. **Second copy of the agent loop.** |

---

## Demo duplicates (FORBIDDEN — must be eliminated)

The agent-demo (`docs-site/agent-demo/index.html`) is architecturally distinct from the
extension popup: it calls the fine-tuned Gemma4 v7-dpo model hosted on HuggingFace Spaces
and renders the structured `{final_answer, transcript, tool_calls}` response. It does **not**
route through the extension popup's `runLocalAgent` path.

However, the demo bundles several dead code blocks that mirror extension or SDK logic. Dead
code is still a drift surface: it confuses contributors and may be cargo-culted into future
forks against the wrong canonical source.

Additionally, `docs-site/chrome_shim_prod.js` contains a live (not dead) agent handler that
is a third copy of the intent-classification loop, independent of both `runLocalAgent` and
the demo's HF Space path.

| Demo location | Mirrors which extension function | Live or dead | Severity | Recommended fix |
|---|---|---|---|---|
| `docs-site/agent-demo/index.html:238-274` — `TOOL_CALL_RE`, `FUNC_RE`, `argsToObj()`, `parseToolCalls()`, `stripToolCalls()` | `src/sdk/canvas_sdk/tool_parser.py` (Python canonical) | **Dead** — `parseToolCalls` is never called; `runAgent()` consumes `payload.tool_calls` from the HF Space directly | HIGH (drift surface) | Delete all five identifiers. The HF Space returns pre-parsed tool calls — the browser never needs to parse raw model output. |
| `docs-site/agent-demo/index.html:184-224` — `MOCK_DATA` object | `CanvasClient` endpoint responses (courses, assignments, grades, announcements, calendar, study) | **Dead** — `dispatchMock` is never called inside `runAgent()` | HIGH (drift surface) | Delete `MOCK_DATA` and `dispatchMock`. Mock data belongs to the HF Space's server-side tool harness, not the browser UI. |
| `docs-site/agent-demo/index.html:156-175` — `TOOL_CATALOG` array | `src/sdk/canvas_sdk/agent_tools/` registry (18 tools, same names) | **Dead** — `TOOL_CATALOG` is never referenced in any JS logic; it appears for display only | MED | Either delete it, or move it into a `const` that populates a visible "Available tools" UI section, and ensure names are kept in sync by deriving from a single source (see §Recommended refactor). |
| `docs-site/chrome_shim_prod.js:50-72` — `AGENT_QUERY` handler | `extension/src/background.js:124` `runLocalAgent()` | **Live** — executed when the extension popup is mounted via the shim on GitHub Pages | HIGH (third copy of agent loop) | Collapse to a stub that returns `{ok: false, error: "agent not available in static demo"}` and route agent queries to the HF Space instead — same as `agent-demo/index.html` already does. Or: delete the shim's intent classifier entirely and rely on the popup already handling `agentQuery` through its own `runLocalAgent` path (the shim only needs to forward the message, not re-implement the handler). |

### Chain of duplication (full picture)

Four implementations of the same agent-query contract exist simultaneously:

```
1. src/sdk/canvas_sdk/ CanvasAgent.run()  ← Python canonical, single source of truth
2. extension/src/background.js runLocalAgent()  ← JS reimplementation (HIGH, prior audit #2)
3. docs-site/chrome_shim_prod.js AGENT_QUERY handler  ← shim reimplementation (HIGH, this audit)
4. docs-site/agent-demo/index.html parseToolCalls + MOCK_DATA  ← dead reimplementation (HIGH, this audit)
```

The target state is one path: #1 only, with #2 collapsed to a native-host pass-through and
#3/#4 deleted entirely.

---

## Recommended refactor (concrete steps)

Two paths are viable. Path A is lower-cost and requires no new build pipeline.

### Path A — Mount the extension popup via the shim (recommended, no build step)

The extension popup (`extension/src/popup/index.html` + `app.js`) already renders a full agent
UI including the chat tab. `docs-site/chrome_shim_prod.js` already stubs the Chrome API
surface so the popup runs on GitHub Pages from static JSON files.

1. Serve the extension popup from `docs-site/` using the existing shim — the "agent demo"
   page becomes the popup itself, not a parallel UI.
2. Delete the `docs-site/agent-demo/index.html` parallel agent shell (or preserve as a
   standalone HF Space demo page, clearly scoped to HF Space calls only — not extension logic).
3. In `chrome_shim_prod.js` `AGENT_QUERY` handler: replace the regex intent classifier with
   a direct call to `callHFSpace()` (imported or inlined from the agent-demo JS) so the shim
   and the standalone demo share one HF Space call function.
4. Delete `MOCK_DATA`, `dispatchMock`, `TOOL_CATALOG`, `parseToolCalls`, `argsToObj`,
   `stripToolCalls` from `agent-demo/index.html`.

**Trade-off:** the popup UI (dark/light toggle, tab nav, grades view) replaces the
agent-demo's minimal chat shell. Acceptable for a demo; may require style tuning.

### Path B — Shared ES module bundle (matches brief default)

1. Extract `extension/src/lib/canvas-client.js` and `extension/src/lib/reranker.js` into a
   shared `docs-site/agent-demo/lib/canvas-shared.js` (plain ES module, no Chrome deps).
2. Add an `esbuild` build step to `extension/package.json` (currently has **no build step** —
   only `jest` test scripts). This is a non-trivial addition: the extension currently ships
   as raw MV3 ES modules; bundling for the demo requires a separate entrypoint and output
   target.
3. Import `CanvasClient` in the demo via `<script type="module">` or a bundled UMD file.
4. Delete `MOCK_DATA`, `dispatchMock`, `TOOL_CATALOG`, `parseToolCalls` from `agent-demo/index.html`.
5. Collapse `chrome_shim_prod.js` `AGENT_QUERY` handler to a stub or HF Space delegate.

**Trade-off:** Path B adds a build pipeline that doesn't exist today. `CanvasClient` has a
hard dependency on `getSetting`/`setSetting` from `cache.js` (IndexedDB, Chrome storage) —
the shared module would need those deps stripped or shimmed for non-extension environments.
Estimated additional work: 1–2 days for build config + shim layer.

---

## Estimated effort

### Deleting dead code (no architectural decision needed — do this first)

| Action | Lines deleted | Files touched | Risk |
|---|---|---|---|
| Delete `TOOL_CALL_RE`, `FUNC_RE`, `argsToObj`, `parseToolCalls`, `stripToolCalls` from `agent-demo/index.html` | ~37 | 1 | LOW — dead code, zero runtime impact |
| Delete `MOCK_DATA`, `dispatchMock` from `agent-demo/index.html` | ~48 | 1 | LOW — dead code |
| Delete or de-duplicate `TOOL_CATALOG` from `agent-demo/index.html` | ~19 | 1 | LOW |

**Total dead-code deletion: ~104 lines, 1 file, zero risk.**

### Path A (recommended)

- Lines moved: ~0 (popup already exists)
- Lines deleted: ~200 (agent-demo parallel shell, chrome_shim AGENT_QUERY classifier)
- Lines added: ~30 (HF Space delegate in shim, minor wiring)
- Files touched: `docs-site/agent-demo/index.html`, `docs-site/chrome_shim_prod.js`
- Risk: LOW — no new build tooling; reuses existing shim contract

### Path B (bundle approach)

- Lines moved: ~169 (`canvas-client.js` → shared lib)
- Lines deleted: ~104 (dead demo code) + ~72 (shim classifier)
- Lines added: ~80 (build config, shim layer for cache deps)
- Files touched: `extension/package.json`, `extension/src/lib/canvas-client.js`, new `docs-site/agent-demo/lib/canvas-shared.js`, `docs-site/chrome_shim_prod.js`, `docs-site/agent-demo/index.html`
- Risk: MED — adds esbuild dependency; `cache.js` IndexedDB coupling needs resolution

---

## Decision needed from user

1. **Reuse path:** Path A (popup via shim, no build step) or Path B (shared ES module bundle with new esbuild pipeline)?
2. **Dead code:** Delete `MOCK_DATA` / `parseToolCalls` / `TOOL_CATALOG` from `agent-demo/index.html` immediately as a standalone no-risk PR? (Recommended regardless of path choice.)
3. **`chrome_shim_prod.js` AGENT_QUERY handler:** collapse to HF Space delegate, or delete entirely and rely on the popup's `runLocalAgent` fallback?
4. **Shared-bundle path (Path B only):** default `docs-site/agent-demo/lib/canvas-shared.js`
5. **Build step (Path B only):** esbuild is the natural fit given MV3 ES module structure; webpack/rollup also viable.

---

## Relationship to prior audit

REVIEW-extension-sdk.md finding #2 (`runLocalAgent` in `background.js`) and finding #3
(`RANK_PROMPT_TEMPLATE` drift) remain open. This audit adds two new instances of the same
pattern — shim `AGENT_QUERY` (live) and demo `parseToolCalls`/`MOCK_DATA` (dead) — and
documents the full four-copy chain. The refactor order should be:

1. Delete dead demo code (zero risk, immediate)
2. Resolve finding #2 (collapse `runLocalAgent` to native-host) — prerequisite for Path A
3. Collapse shim `AGENT_QUERY` to a stub / HF Space delegate
4. Path A or B for long-term sharing
