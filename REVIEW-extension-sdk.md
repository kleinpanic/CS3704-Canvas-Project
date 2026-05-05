# Extension ↔ SDK Architectural Audit (Phase 19, Task 3)

**Audit date:** 2026-05-05
**Audited tree:** `extension/` (manifest v3 Chrome extension, JS)
**Reference:** `src/sdk/canvas_sdk/` (Python agent, tool parser, backends)

## Architectural contract

**The extension is presentation only. The SDK is the single source of agent logic.**

| Layer | Responsibility | Forbidden |
|-------|----------------|-----------|
| **Extension** (JS, MV3) | Popup UI, badges, notifications, Canvas-API thin client used for foreground reads, native-messaging port | Tool-call parsing, agent loops, prompt templates, model HTTP clients |
| **Native messaging host** (Python, `canvas_sdk.host`) | stdio bridge between extension and SDK | — |
| **canvas_sdk** (Python) | `CanvasAgent`, `tool_parser`, backends (`gemma4_backend`, `gemini_backend`), tool registry | UI concerns |

```
┌─────────────────────────┐       Native Messaging          ┌────────────────────┐
│   Extension (JS, MV3)   │ ◄───────── stdio ─────────────► │  canvas_sdk.host   │
│                         │     {id, method, params}        │  (Python broker)   │
│  ┌──────────────────┐   │                                 └─────────┬──────────┘
│  │  popup/app.js    │   │                                           │
│  │  background.js   │   │                                           ▼
│  │  lib/canvas-     │   │                                 ┌────────────────────┐
│  │     client.js    │   │                                 │   CanvasAgent      │
│  │  lib/native-     │   │                                 │   (agent loop)     │
│  │     host.js      │   │                                 │                    │
│  └──────────────────┘   │                                 │   tool_parser      │
│                         │                                 │   backends.*       │
└─────────────────────────┘                                 └────────────────────┘
```

The extension MUST NOT:

1. Implement its own tool-call regex (`<|tool_call>...<tool_call|>`)
2. Run an agent loop (LLM-call → parse tools → dispatch → re-prompt)
3. Talk directly to a model HTTP endpoint (Ollama, vLLM, OpenAI, Gemini)

Whenever the extension needs an LLM-driven answer, it sends `{type: 'AGENT_QUERY', query}` to
the background worker, which forwards to the native-messaging host. The host invokes
`CanvasAgent.run(query)` and returns `{answer, transcript, tool_calls}`.

---

## Findings

Searches performed:

```bash
grep -rn "tool_call" extension/ --include='*.js' --include='*.ts'      # 0 hits
grep -rn -E "openai|vllm|generate|completion" extension/ --include='*.js'  # 0 hits
grep -rn -E "agent|llm|gemma|gemini|chatcompletion|prompt" extension/ -i  # see below
```

### Severity legend
- **HIGH** — full reimplementation of SDK logic; replace with native-host call
- **MEDIUM** — partial duplication; refactor to thin pass-through
- **LOW** — stub or naming overlap only; document and move on

| # | Severity | File:line | Issue | Recommendation |
|---|----------|-----------|-------|----------------|
| 1 | **HIGH** | `extension/src/lib/reranker.js:112-171` | `OllamaReranker` class talks directly to `http://localhost:11434/api/chat`, bundles its own `RANK_PROMPT_TEMPLATE` and pairwise-scoring algorithm. This is a parallel agent path that bypasses `canvas_sdk` entirely. | TODO: route ranking through `AGENT_QUERY` → native host → `canvas_sdk.tools.reranker.rank_assignments`. Delete `OllamaReranker`. The `RANK_PROMPT_TEMPLATE` must live in the SDK only (or be re-exported by SDK at training time). |
| 2 | **HIGH** | `extension/src/background.js:108-276` | `runLocalAgent(query)` is a deterministic agent loop with intent classification (regex on query), tool dispatch (`canvas.get_courses`, `canvas.get_grades`, `canvas.list_announcements`, etc.), and a manual fall-through to native host for "complex" queries. This duplicates `CanvasAgent.run(...)` semantics. | TODO: collapse `runLocalAgent` to a single `nativeCall('agentQuery', token, baseUrl, {query})`. The native host is already wired (line 268 falls through to it); make it the only path. Keep the regex-based intent classifier only as a transient offline-safe fallback gated behind a feature flag. |
| 3 | **MEDIUM** | `extension/src/lib/reranker.js:34-49` | `RANK_PROMPT_TEMPLATE` and `getRankPromptFormatSha()` duplicate constants that exist on the training side (`src/canvas_tui/reranker.py`). The SHA matching is the contract; if the strings ever drift, models trained on the canonical template score wrong. | TODO: generate the JS template constant from the Python source at build time (e.g., `python -m canvas_sdk.tools.reranker --emit-js > extension/src/lib/_reranker_template.generated.js`). Mark hand-edits as forbidden in CONTRIBUTING. |
| 4 | **LOW** | `extension/src/lib/extension-contract.js:33-34` (`agentQuery: 'AGENT_QUERY'`) and `extension-api.js:93-95` | Naming overlap is intentional and correct — these are message-type constants for the bridge. No code duplication. | No action. |
| 5 | **LOW** | `extension/src/lib/canvas-client.js` | Direct Canvas API client used for foreground reads (assignments, courses, grades). This is presentation-layer caching, not agent logic. The SDK has its own Canvas client but the extension's is justified for offline-friendly badge/notification updates that must work without the native host installed. | No action — document the dual-client decision in `docs-site/extension.md`. |

### Search verification

| Pattern | Hits in `extension/` | Status |
|---------|---------------------|--------|
| `<\|tool_call>` regex | 0 | clean |
| `tool_call\|>` regex | 0 | clean |
| `chat completion` / `openai` / `vllm` / `generate` / `completion` | 0 | clean |
| `gemma` (LLM model name) | 4 (all in `reranker.js` referencing `gemma4-canvas-reranker:Q5_K_M` model **name**, no inference logic) | document |
| `gemini` | 0 | clean |
| Direct LLM HTTP fetch | 1 (`reranker.js:127` → Ollama `/api/chat`) | **finding #1** |
| Agent loop | 1 (`background.js:124` `runLocalAgent`) | **finding #2** |

---

## Refactor scope (for follow-up PR — NOT this PR)

This audit PR documents the contract and the duplications. The actual refactor is its own
follow-up. Scope estimate:

1. **Finding #1** — delete `OllamaReranker`, route through native host. ~150 LOC delete, ~30 LOC add.
2. **Finding #2** — collapse `runLocalAgent` to `nativeCall('agentQuery', ...)`. ~170 LOC delete, ~10 LOC add. Optional: keep a regex-based stub behind `if (settings.offlineFallback)` for users who never install the native host.
3. **Finding #3** — generate JS template from Python at build time. ~50 LOC build script, ~20 LOC delete.

**Risk gate:** the refactor should land *after* the native host's `agentQuery` method is verified to handle all six intents currently in `runLocalAgent` (grades, prioritize, study plan, announcements, due, courses). Add an extension test matrix `tests/agent-intents.test.js` that calls each intent through the bridge.

---

## Why this matters

The DPO-trained v7 model scores **94.2% reward accuracy** on the held-out preference set
(see [bench comparison](https://github.com/kleinpanic/CS3704-DPO-SSOT/blob/main/docs/bench_v7_comparison.md))
— but only when consumers route through the canonical `tool_parser` and prompt format. Any
extension-side reimplementation creates a silent drift surface where the model is asked to
score in one format and then evaluated in another, exactly the failure mode that produced
the v1 "DPO ≡ SFT identity" artifact (see DPO-SSOT paper §6.5).

The contract above is the protection: extension is presentation only, SDK is the only
agent. One implementation, one prompt template, one tool parser, one truth.
