"""
benchmark_quants.py — pairwise accuracy + latency benchmark across all
GGUF quantization levels on the v3 held-out test set.

For each quant in {Q4_K_M, Q5_K_M, Q6_K, Q8_0, f16}:
  - Load via llama-cpp-python (n_gpu_layers=-1 for full GPU offload)
  - For each of the 148 held-out pairs, send the chat-templated prompt
    and greedy-decode the response (max 32 new tokens)
  - Time each call (warm-state, after one warmup round)
  - Parse the first "Item A"/"Item B" mention from the generation
  - Compare to the gold extracted from the chosen text
  - Report: pairwise accuracy + Wilson 95% CI + per-call latency stats

Output: checkpoints/benchmark/quants_benchmark.json with per-quant
results for paper Table 3 / HF model card "Quantization quality
comparison" entry.

Run after multi-quant generation. Wall time: ~20 min for 5 quants × 148
pairs at ~300ms/call warm.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

GGUF_DIR = Path("checkpoints/gguf")
TEST_PATH = Path("data/dpo_test_v3.jsonl")
OUT_PATH = Path("checkpoints/benchmark/quants_benchmark.json")

QUANTS = [
    "Q4_K_M",
    "Q5_K_M",
    "Q6_K",
    "Q8_0",
    "f16",
]

ITEM_LEAD = re.compile(r"\bItem\s*([AB])\b")


def chosen_picks(text: str) -> str | None:
    m = ITEM_LEAD.search(text)
    return m.group(1).upper() if m else None


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def benchmark_quant(quant_name: str, pairs: list[dict]) -> dict:
    from llama_cpp import Llama

    gguf_path = GGUF_DIR / f"gemma4-reranker-{quant_name}.gguf"
    if not gguf_path.exists():
        return {"quant": quant_name, "error": f"missing {gguf_path}"}

    print(f"\n[{quant_name}] loading {gguf_path.name} ({gguf_path.stat().st_size/1024**3:.2f} GiB)")
    t0 = time.time()
    llm = Llama(
        model_path=str(gguf_path),
        n_ctx=1024,
        n_gpu_layers=-1,
        verbose=False,
        seed=42,
    )
    load_time = time.time() - t0
    print(f"[{quant_name}] loaded in {load_time:.1f}s")

    # Warm-up call so the first measured call isn't cold-start
    _ = llm.create_chat_completion(
        messages=[{"role": "user", "content": "warmup"}],
        max_tokens=4,
        temperature=0.0,
    )

    n_correct = 0
    n_abstain = 0
    warm_warm_latencies_ms: list[float] = []
    cold_call_ms = None

    for i, pair in enumerate(pairs):
        prompt = pair["prompt"]
        gold = chosen_picks(pair["chosen"])

        t0 = time.time()
        response = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=32,
            temperature=0.0,
        )
        dt_ms = (time.time() - t0) * 1000
        if i == 0:
            # First measured call is cold (despite the warmup_call above
            # priming the model load, the first real-prompt call still
            # sees first-token-position cache misses). Excluded from the
            # warm distribution per codex cross-audit.
            cold_call_ms = dt_ms
        else:
            warm_warm_latencies_ms.append(dt_ms)

        text = response["choices"][0]["message"]["content"]
        pred = chosen_picks(text)
        if pred is None:
            n_abstain += 1
        elif pred == gold:
            n_correct += 1

        if (i + 1) % 25 == 0:
            print(f"  [{i+1:3d}/{len(pairs)}] correct={n_correct}  mean_ms={sum(warm_latencies_ms)/len(warm_latencies_ms):.0f}")

    n_scored = len(pairs) - n_abstain
    acc = n_correct / n_scored if n_scored else 0.0
    lo, hi = wilson_ci(n_correct, n_scored)
    sorted_lat = sorted(warm_latencies_ms)
    mid = len(sorted_lat) // 2

    return {
        "quant": quant_name,
        "gguf_path": str(gguf_path),
        "size_gib": round(gguf_path.stat().st_size / 1024**3, 2),
        "load_seconds": round(load_time, 1),
        "n_pairs": len(pairs),
        "n_correct": n_correct,
        "n_scored": n_scored,
        "n_abstain": n_abstain,
        "pairwise_accuracy": round(acc, 4),
        "wilson_95ci": [round(lo, 4), round(hi, 4)],
        "latency_ms": {
            "cold_first_call": round(cold_call_ms, 1) if cold_call_ms else None,
            "warm_min": round(sorted_lat[0], 1),
            "warm_p25": round(sorted_lat[len(sorted_lat)//4], 1),
            "warm_median": round(sorted_lat[mid], 1),
            "warm_p75": round(sorted_lat[3*len(sorted_lat)//4], 1),
            "warm_max": round(sorted_lat[-1], 1),
            "warm_mean": round(sum(sorted_lat)/len(sorted_lat), 1),
        },
    }


def main():
    pairs = [json.loads(l) for l in TEST_PATH.read_text().splitlines() if l.strip()]
    print(f"[load] {len(pairs)} held-out pairs from {TEST_PATH}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    results = {
        "test_data": str(TEST_PATH),
        "n_pairs": len(pairs),
        "test_partition": "v3 item-disjoint, 148 standard pairs (zero hard-neg)",
        "results": {},
    }

    for q in QUANTS:
        results["results"][q] = benchmark_quant(q, pairs)
        OUT_PATH.write_text(json.dumps(results, indent=2))
        print(f"[saved] {OUT_PATH}")

    print(f"\n{'='*70}")
    print(f"  QUANT BENCHMARK SUMMARY  (n={len(pairs)})")
    print(f"{'='*70}")
    print(f"  {'Quant':10s}  {'GiB':>5}  {'Acc':>6}  {'CI':>20}  {'Med ms':>8}  {'Mean ms':>8}")
    for q in QUANTS:
        r = results["results"].get(q, {})
        if "error" in r:
            print(f"  {q:10s}  ERROR: {r['error']}")
            continue
        ci = r.get("wilson_95ci", [0,0])
        ci_str = f"[{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]"
        l = r.get("latency_ms", {})
        print(f"  {q:10s}  {r.get('size_gib',0):>5.2f}  {r.get('pairwise_accuracy',0)*100:>5.1f}%  {ci_str:>20}  {l.get('warm_median',0):>8.1f}  {l.get('warm_mean',0):>8.1f}")
    print(f"\nFull report: {OUT_PATH}")


if __name__ == "__main__":
    main()
