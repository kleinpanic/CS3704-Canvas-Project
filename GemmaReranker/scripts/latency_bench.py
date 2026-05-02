#!/usr/bin/env python3
"""
latency_bench.py — INT-03: verify LocalReranker sorts 10 items in under 500ms.

Uses the LocalReranker directly (requires llama-cpp-python + GGUF).
Runs 3 trials and reports min/mean/max wall-clock time for 10-item sort.

Usage:
  python source/latency_bench.py --gguf checkpoints/gguf/gemma4-reranker-Q5_K_M.gguf
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

TEST_DATA = "/tmp/canvas-review/GemmaReranker/data/test.jsonl"
N_ITEMS = 10
N_TRIALS = 3
TARGET_MS = 500


def make_fake_items(n: int):
    sys.path.insert(0, "/tmp/canvas-review/src")
    from canvas_tui.models.item import CanvasItem

    records = [json.loads(l) for l in open(TEST_DATA)]
    items = []
    seen = set()
    for rec in records:
        raw = rec.get("item_a", {})
        if isinstance(raw, str):
            try:
                raw = json.loads(raw.replace("'", '"'))
            except Exception:
                continue
        title = raw.get("title", "?")
        if title not in seen:
            seen.add(title)
            items.append(CanvasItem(
                title=title,
                ptype=raw.get("type", "assignment").lower(),
                course_code=raw.get("course", "COURSE0"),
                due_at=raw.get("due_at") or "",
                points=raw.get("points"),
            ))
        if len(items) >= n:
            break
    return items[:n]


def run_latency_bench(gguf_path: str) -> None:
    sys.path.insert(0, "/tmp/canvas-review/src")
    from canvas_tui.reranker import LocalReranker

    print(f"Loading GGUF: {gguf_path}")
    reranker = LocalReranker(gguf_path)
    items = make_fake_items(N_ITEMS)
    print(f"Loaded {len(items)} items. Running {N_TRIALS} trials of {N_ITEMS}-item sort...")

    times_ms = []
    for trial in range(N_TRIALS):
        t0 = time.perf_counter()
        reranker.rank("urgent assignments due soon", items)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        times_ms.append(elapsed_ms)
        print(f"  Trial {trial+1}: {elapsed_ms:.0f}ms")

    min_ms = min(times_ms)
    mean_ms = sum(times_ms) / len(times_ms)
    max_ms = max(times_ms)
    print(f"\nLatency: min={min_ms:.0f}ms  mean={mean_ms:.0f}ms  max={max_ms:.0f}ms")
    print(f"Target: {TARGET_MS}ms")

    if mean_ms <= TARGET_MS:
        print(f"PASS: mean {mean_ms:.0f}ms ≤ {TARGET_MS}ms (INT-03)")
    else:
        print(f"FAIL: mean {mean_ms:.0f}ms > {TARGET_MS}ms (INT-03)")
        sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gguf", default="checkpoints/gguf/gemma4-reranker-Q5_K_M.gguf")
    args = p.parse_args()
    if not Path(args.gguf).exists():
        print(f"ERROR: GGUF not found: {args.gguf}", file=sys.stderr)
        sys.exit(1)
    run_latency_bench(args.gguf)


if __name__ == "__main__":
    main()
