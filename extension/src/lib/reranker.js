/**
 * canvas-tui browser extension — reranker client (Phase 01.1, JS port).
 *
 * Mirrors src/canvas_tui/reranker.py from the Python TUI side. Same
 * RANK_PROMPT_TEMPLATE, same SHA, same serializeItem semantics, so a
 * model trained on the canonical pipeline scores items consistently
 * across both consumers.
 *
 * Backends:
 *   NullReranker         — no-op pass-through. Default when
 *                          settings.useAiReranker === false.
 *   OllamaReranker       — HTTP POST to http://localhost:11434
 *                          (Ollama default). Best MV3-friendly
 *                          choice — no in-extension WASM, no model
 *                          bundling. User must install Ollama and
 *                          pull a kleinpanic93/gemma4-canvas-reranker
 *                          quant locally. Falls back to NullReranker
 *                          if the endpoint is unreachable.
 *
 * Per the v3 held-out validation in the upstream paper §6.6, DPO and
 * the QLoRA-merged BF16 reference produce identical predictions.
 *
 * Quant choice (per source/benchmark_quants.py on n=148 held-out):
 *   - Q5_K_M (3.4 GiB) — 98.0% accuracy, recommended default
 *   - Q4_K_M (3.18 GiB) — 93.2% accuracy, ~5pp lower than Q5; use only
 *     if you need the smaller binary and accept the accuracy hit
 *
 * Default backend below pulls Q4_K_M to favor the small-binary
 * extension footprint, but consumers should consider switching to
 * Q5_K_M (`gemma4-canvas-reranker:Q5_K_M`) if accuracy on standard
 * pairs matters more than ~200 MiB of disk.
 */

export const RANK_PROMPT_TEMPLATE =
  "Which Canvas item is more urgent and why?\n\n" +
  "[Query]: {query}\n" +
  "Item A: {item_a}\n" +
  "Item B: {item_b}";

let _shaCache = null;
export async function getRankPromptFormatSha() {
  if (_shaCache !== null) return _shaCache;
  const data = new TextEncoder().encode(RANK_PROMPT_TEMPLATE);
  const buf = await crypto.subtle.digest("SHA-256", data);
  _shaCache = Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return _shaCache;
}

const _BADGE_MAP = {
  assignment: "ASGN",
  quiz: "QUIZ",
  exam: "EXAM",
  discussion: "DISC",
  event: "EVNT",
  announcement: "NOTE",
};

async function _anonymizeCourse(courseCode) {
  const data = new TextEncoder().encode((courseCode || "").trim());
  const buf = await crypto.subtle.digest("SHA-256", data);
  const arr = new Uint8Array(buf);
  const intVal = (arr[0] << 24) | (arr[1] << 16) | (arr[2] << 8) | arr[3];
  const positive = intVal >>> 0;
  return `COURSE${(positive % 9000) + 1000}`;
}

function _dueLabel(dueIso) {
  if (!dueIso) return null;
  const dt = new Date(dueIso);
  if (isNaN(dt.getTime())) return null;
  const deltaH = (dt.getTime() - Date.now()) / 3600000;
  if (deltaH < -1) return "OVERDUE";
  if (deltaH < 24) return "Today";
  if (deltaH < 48) return "Tomorrow";
  const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(dt.getUTCDate()).padStart(2, "0");
  const hh = String(dt.getUTCHours()).padStart(2, "0");
  const mi = String(dt.getUTCMinutes()).padStart(2, "0");
  return `Due ${mm}/${dd} ${hh}:${mi}`;
}

export async function serializeItem(item) {
  const parts = [];
  const ptype = (item.ptype || "?").toLowerCase();
  parts.push(`[${_BADGE_MAP[ptype] || ptype.slice(0, 4).toUpperCase()}]`);
  parts.push((item.title || "(untitled)").slice(0, 45));
  if (item.course_code) {
    parts.push(`@${await _anonymizeCourse(item.course_code)}`);
  }
  // Mirror src/canvas_tui/models/item.py:serialize_item exactly: the
  // training-side serializer does NOT consume status_flags. Submitted/
  // missing items must be filtered out by the consumer before calling
  // serializeItem; otherwise they get serialized identically to open
  // items.
  const label = _dueLabel(item.due_iso);
  if (label) parts.push(label);
  if (item.points && Number(item.points) > 0) {
    parts.push(`${Math.round(Number(item.points))}pts`);
  }
  return parts.join(" ");
}

export class NullReranker {
  name = "null";
  async rank(_query, items) {
    return [...items];
  }
}

export class OllamaReranker {
  name = "ollama";
  constructor({
    endpoint = "http://localhost:11434",
    model = "gemma4-canvas-reranker:Q4_K_M",
    timeoutMs = 5000,
  } = {}) {
    this.endpoint = endpoint;
    this.model = model;
    this.timeoutMs = timeoutMs;
  }
  async _chat(prompt) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const resp = await fetch(`${this.endpoint}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: this.model,
          messages: [{ role: "user", content: prompt }],
          stream: false,
          options: { temperature: 0, num_predict: 8 },
        }),
        signal: ctrl.signal,
      });
      if (!resp.ok) throw new Error(`ollama HTTP ${resp.status}`);
      const data = await resp.json();
      return data?.message?.content ?? "";
    } finally {
      clearTimeout(t);
    }
  }
  async _scoreItem(query, itemSerialized, refSerialized) {
    const promptA = RANK_PROMPT_TEMPLATE
      .replace("{query}", query)
      .replace("{item_a}", itemSerialized)
      .replace("{item_b}", refSerialized);
    const promptB = RANK_PROMPT_TEMPLATE
      .replace("{query}", query)
      .replace("{item_a}", refSerialized)
      .replace("{item_b}", itemSerialized);
    const [textA, textB] = await Promise.all([this._chat(promptA), this._chat(promptB)]);
    const pickA = /\bItem\s*([AB])\b/i.exec(textA)?.[1]?.toUpperCase();
    const pickB = /\bItem\s*([AB])\b/i.exec(textB)?.[1]?.toUpperCase();
    const lpA = pickA === "A" ? 1 : pickA === "B" ? -1 : 0;
    const lpB = pickB === "A" ? 1 : pickB === "B" ? -1 : 0;
    return lpA - lpB;
  }
  async rank(query, items) {
    if (!items || items.length === 0) return [];
    const ref = "[ASGN] Reference Assignment @COURSE0000 Due 12/31 23:59 50pts";
    const serialized = await Promise.all(items.map((i) => serializeItem(i)));
    const scores = await Promise.all(
      serialized.map((s, idx) => this._scoreItem(query, s, ref).then((sc) => [sc, items[idx]]))
    );
    scores.sort((a, b) => b[0] - a[0]);
    return scores.map(([, item]) => item);
  }
}

export async function makeReranker({
  useAi = false,
  ollamaEndpoint = "http://localhost:11434",
  ollamaModel = "gemma4-canvas-reranker:Q4_K_M",
} = {}) {
  if (!useAi) return new NullReranker();
  try {
    const probe = await fetch(`${ollamaEndpoint}/api/tags`, { signal: AbortSignal.timeout(1000) });
    if (probe.ok) {
      return new OllamaReranker({ endpoint: ollamaEndpoint, model: ollamaModel });
    }
  } catch (_) {
    // fall through
  }
  return new NullReranker();
}
