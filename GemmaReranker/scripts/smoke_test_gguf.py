#!/usr/bin/env python3
"""
smoke_test_gguf.py — EXPORT-02: 20-query pairwise smoke test for the Q5_K_M GGUF.

Loads 20 pairs from the test set, runs the GGUF model via llama-cpp-python,
parses the "Item A" / "Item B" response, and checks against ground-truth preference.

Success criterion: all 20 queries return a parseable response (A or B).
Accuracy is reported but not gated (the benchmark is the authoritative eval).

Usage:
  python source/smoke_test_gguf.py --gguf checkpoints/gguf/gemma4-reranker-Q5_K_M.gguf
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TEST_DATA = os.environ.get(
    "BENCHMARK_TEST_DATA",
    "/tmp/canvas-review/GemmaReranker/data/test.jsonl",
)
N_SAMPLES = 20

RANK_PROMPT_TEMPLATE = (
    "Which Canvas item is more urgent and why?\n\n"
    "[Query]: {query}\n"
    "Item A: {item_a}\n"
    "Item B: {item_b}"
)


def _fmt_item(raw) -> str:
    if isinstance(raw, str):
        try:
            d = json.loads(raw.replace("'", '"'))
        except Exception:
            return raw[:120]
    else:
        d = raw
    parts = [d.get("title", "?"), d.get("type", ""), d.get("course", "")]
    return " | ".join(p for p in parts if p)


def run_smoke_test(gguf_path: str) -> None:
    from llama_cpp import Llama

    print(f"Loading GGUF: {gguf_path}")
    llm = Llama(
        model_path=gguf_path,
        n_ctx=512,
        n_gpu_layers=-1,
        verbose=False,
    )
    print(f"Model loaded. Running {N_SAMPLES} pairwise queries...")

    records = [json.loads(l) for l in open(TEST_DATA)]
    samples = records[:N_SAMPLES]

    correct = 0
    parseable = 0
    for i, rec in enumerate(samples):
        query = rec.get("query", "")
        item_a = _fmt_item(rec["item_a"])
        item_b = _fmt_item(rec["item_b"])
        label = int(rec.get("preference", -1))

        prompt = RANK_PROMPT_TEMPLATE.format(query=query, item_a=item_a, item_b=item_b)
        out = llm.create_completion(prompt, max_tokens=10, temperature=0.0)
        text = out["choices"][0]["text"].strip()

        if "A" in text[:8] or text.startswith("Item A"):
            pred = 1
        elif "B" in text[:8] or text.startswith("Item B"):
            pred = 0
        else:
            pred = -1

        is_parseable = pred != -1
        is_correct = label != -1 and pred == label
        if is_parseable:
            parseable += 1
        if is_correct:
            correct += 1

        marker = "✓" if is_correct else ("?" if not is_parseable else "✗")
        print(f"  [{marker}] pair {i+1:2d}: pred={pred} label={label}  response={text[:40]!r}")

    print(f"\nResults: {parseable}/{N_SAMPLES} parseable, {correct}/{N_SAMPLES} correct")

    if parseable < N_SAMPLES:
        print(f"FAIL: {N_SAMPLES - parseable} queries produced unparseable output")
        sys.exit(1)
    print("PASS: all 20 queries produced parseable A/B responses (EXPORT-02)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gguf", default="checkpoints/gguf/gemma4-reranker-Q5_K_M.gguf")
    args = p.parse_args()
    if not Path(args.gguf).exists():
        print(f"ERROR: GGUF not found: {args.gguf}", file=sys.stderr)
        print("Run: python source/export_gguf.py", file=sys.stderr)
        sys.exit(1)
    run_smoke_test(args.gguf)


if __name__ == "__main__":
    main()
