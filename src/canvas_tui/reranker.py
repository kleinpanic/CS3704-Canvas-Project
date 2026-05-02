"""
canvas_tui.reranker — pluggable reranker for Canvas item priority sort.

Defines:

  RANK_PROMPT_TEMPLATE      — exact prompt text the published model was
                              trained on (canvas_tui mirrors this byte-
                              for-byte; SHA below verifies parity).
  RANK_PROMPT_FORMAT_SHA    — SHA-256 of RANK_PROMPT_TEMPLATE; consumers
                              of this module assert equality with the
                              upstream training pipeline's
                              TRAINING_PROMPT_FORMAT_SHA to fail loudly
                              on schema drift.
  Reranker                  — runtime-checkable Protocol all backends
                              implement.
  NullReranker              — no-op pass-through (returns items in input
                              order). Default when cfg.use_ai_reranker
                              is False.
  AlwaysAReranker           — test harness: always returns items[0]
                              first. Useful in tests that need to verify
                              the urgency-sort dispatch fires.
  LocalReranker             — production GGUF inference via
                              llama-cpp-python. SHA-verified at __init__;
                              reference-differential pointwise scoring at
                              rank().

The default canvas-tui behaviour with `cfg.use_ai_reranker=False` is
NullReranker — the AI reranker is opt-in.
"""
from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from .models.item import CanvasItem, serialize_item

# Mirrors GemmaReranker/scripts/generate_rerank_data.py prompt template
# verbatim. Whitespace and punctuation matter for SHA parity.
RANK_PROMPT_TEMPLATE = (
    "Which Canvas item is more urgent and why?\n\n"
    "[Query]: {query}\n"
    "Item A: {item_a}\n"
    "Item B: {item_b}"
)

RANK_PROMPT_FORMAT_SHA = hashlib.sha256(
    RANK_PROMPT_TEMPLATE.encode("utf-8")
).hexdigest()


@runtime_checkable
class Reranker(Protocol):
    """Reranker contract — every backend implements this single method."""

    def rank(self, query: str, items: list[CanvasItem]) -> list[CanvasItem]:
        """Return items sorted by predicted urgency, most urgent first."""
        ...


class NullReranker:
    """Order-preserving pass-through. Default for `use_ai_reranker=False`."""

    def rank(self, query: str, items: list[CanvasItem]) -> list[CanvasItem]:
        return list(items)


class AlwaysAReranker:
    """Test harness: items[0] always first. Used in
    test_integration_sha to prove the urgency dispatch fires."""

    def rank(self, query: str, items: list[CanvasItem]) -> list[CanvasItem]:
        if not items:
            return []
        return [items[0]] + list(items[1:])


# ── Pointwise reference item — same constant used in GemmaReranker/
# scripts/benchmark.py so the LocalReranker.rank() differential
# scoring matches the offline benchmark harness exactly. Captures a
# "moderately urgent" anchor against which test items are scored.
_POINTWISE_REF_ITEM_SERIALIZED = "[ASGN] Reference Assignment @COURSE0000 Due 12/31 23:59 50pts"


class LocalReranker:
    """GGUF-backed reranker via llama-cpp-python.

    Constructor arguments:
        model_path:    path to a .gguf file (any of the published quants
                       at huggingface.co/kleinpanic93/gemma4-canvas-reranker)
        expected_sha:  optional 64-char hex string — if provided, must
                       equal RANK_PROMPT_FORMAT_SHA or __init__ raises.
                       Production callers pass
                       expected_sha=RANK_PROMPT_FORMAT_SHA so any future
                       template drift fails immediately at startup.
        n_gpu_layers:  llama.cpp GPU offload knob. -1 = full offload.
        n_ctx:         context window. 1024 is plenty for two items
                       plus the rationale.

    Inference path: reference-differential pointwise scoring. For each
    item, compute logprob_delta = logprob(model says item is more
    urgent than reference) - logprob(model says reference is more
    urgent than item), then sort items descending by delta. Same
    method `GemmaReranker/scripts/benchmark.py:score_item` uses.

    Per the v3 held-out validation, DPO and the QLoRA-merged BF16
    base produce identical predictions — recommend pointing model_path
    at gemma4-reranker-Q5_K_M.gguf or smaller (Q4_K_M for browser/edge
    deployment).
    """

    def __init__(
        self,
        model_path: str,
        expected_sha: str | None = None,
        n_gpu_layers: int = -1,
        n_ctx: int = 1024,
    ) -> None:
        if expected_sha is not None and expected_sha != RANK_PROMPT_FORMAT_SHA:
            raise ValueError(
                f"RANK_PROMPT_FORMAT_SHA mismatch: "
                f"expected {expected_sha}, got {RANK_PROMPT_FORMAT_SHA}. "
                "Refusing to load — the trained template and the consumer "
                "template have drifted; rerunning the data pipeline is "
                "required."
            )
        self.model_path = model_path
        self._n_gpu_layers = n_gpu_layers
        self._n_ctx = n_ctx
        self._llm = None  # lazy: only load when rank() is first called

    def _ensure_loaded(self) -> None:
        if self._llm is not None:
            return
        if not self.model_path:
            raise NotImplementedError(
                "LocalReranker constructed with empty model_path; set "
                "Config.model_path to a downloaded .gguf before enabling "
                "use_ai_reranker."
            )
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise ImportError(
                "LocalReranker requires the [ai] extra. Install with: "
                "`pip install canvas-tui[ai]` or "
                "`pip install llama-cpp-python`."
            ) from exc
        self._llm = Llama(
            model_path=self.model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            verbose=False,
            seed=42,
        )

    def _call_model(self, prompt: str) -> float:
        """Return logprob of "Item A is more urgent" vs "Item B is more
        urgent" given the formatted prompt. Positive → A wins,
        negative → B wins."""
        self._ensure_loaded()
        out = self._llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8,
            temperature=0.0,
            logprobs=True,
        )
        text = out["choices"][0]["message"]["content"]
        # Greedy parse of the model's argued winner (matches the
        # validate_dpo_holdout.py gold extraction strategy).
        import re
        m = re.search(r"\bItem\s*([AB])\b", text)
        if m is None:
            return 0.0
        return 1.0 if m.group(1).upper() == "A" else -1.0

    def rank(self, query: str, items: list[CanvasItem]) -> list[CanvasItem]:
        if not items:
            return []
        scores: list[tuple[float, CanvasItem]] = []
        for item in items:
            item_serialized = serialize_item(item)
            # Two-call differential vs the pointwise reference, matching
            # GemmaReranker/scripts/benchmark.py::score_item's design.
            prompt_a = RANK_PROMPT_TEMPLATE.format(
                query=query,
                item_a=item_serialized,
                item_b=_POINTWISE_REF_ITEM_SERIALIZED,
            )
            prompt_b = RANK_PROMPT_TEMPLATE.format(
                query=query,
                item_a=_POINTWISE_REF_ITEM_SERIALIZED,
                item_b=item_serialized,
            )
            lp_a = self._call_model(prompt_a)   # +1 if model picks item-in-slot-A (the test item)
            lp_b = self._call_model(prompt_b)   # -1 if model picks item-in-slot-B (the test item)
            score = lp_a - lp_b                  # large positive = item is consistently chosen
            scores.append((score, item))
        scores.sort(key=lambda s: s[0], reverse=True)
        return [item for _, item in scores]
