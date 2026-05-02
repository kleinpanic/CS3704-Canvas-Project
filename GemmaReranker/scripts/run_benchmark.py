"""
run_benchmark.py — Phase 06 benchmark for Canvas item reranking.

Scores one model variant against the 827-pair held-out test set.
Metrics: pairwise accuracy, Kendall's tau, NDCG@5 (per query group).
Per-pair-type breakdown: standard, equivalence, contrast, same-course, cross-course.

Usage (inside training container):
  python source/run_benchmark.py --variant sft --checkpoint /sft-checkpoint
  python source/run_benchmark.py --variant lora \\
      --checkpoint google/gemma-4-E2B-it --adapter /lora-adapter
  python source/run_benchmark.py --variant dpo --checkpoint /dpo-checkpoint
  python source/run_benchmark.py --variant heuristic  # no model needed

Then aggregate:
  python source/run_benchmark.py --aggregate
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
from datetime import datetime

TEST_DATA = os.environ.get(
    "BENCHMARK_TEST_DATA",
    "/tmp/canvas-review/GemmaReranker/data/test.jsonl",
)
OUTPUT_DIR = pathlib.Path("./checkpoints/benchmark")
AGGREGATE_REPORT = OUTPUT_DIR / "benchmark_report.json"

PAIR_TYPES = ["standard", "equivalence", "contrast", "same-course", "cross-course"]


# ── Prompt ──────────────────────────────────────────────────────────────────


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


def build_prompt(record: dict) -> str:
    query = record.get("query", "")
    a = _fmt_item(record["item_a"])
    b = _fmt_item(record["item_b"])
    return (
        f"Query: {query}\n"
        f"Item A: {a}\n"
        f"Item B: {b}\n"
        f"Which item requires more urgent attention? Answer with exactly one letter:"
    )


# ── Scoring ─────────────────────────────────────────────────────────────────


def heuristic_predict(record: dict) -> int:
    try:
        ua = float(record["urgency_a"])
        ub = float(record["urgency_b"])
        if ua > ub:
            return 1
        elif ub > ua:
            return 0
        else:
            return -1
    except (KeyError, ValueError):
        return -1


def model_predict(model, tokenizer, prompt: str, device) -> int:
    import torch

    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.inference_mode():
        logits = model(**inputs).logits[0, -1, :]

    tok_A = tokenizer.encode("A", add_special_tokens=False)
    tok_B = tokenizer.encode("B", add_special_tokens=False)
    if not tok_A or not tok_B:
        return -1

    score_A = float(logits[tok_A[0]])
    score_B = float(logits[tok_B[0]])

    if score_A > score_B:
        return 1
    elif score_B > score_A:
        return 0
    else:
        return -1


# ── Metrics ─────────────────────────────────────────────────────────────────


def pairwise_accuracy(predictions: list[int], labels: list[int]) -> float:
    correct = sum(1 for p, l in zip(predictions, labels) if l != -1 and p == l)
    total = sum(1 for l in labels if l != -1)
    return correct / total if total > 0 else 0.0


def kendall_tau(predictions: list[int], labels: list[int]) -> float:
    acc = pairwise_accuracy(predictions, labels)
    return 2 * acc - 1.0


def ndcg_at_5(records: list[dict], predictions: list[int]) -> float:
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for rec, pred in zip(records, predictions):
        groups[rec.get("query", "default")].append((rec, pred))

    ndcg_scores = []
    for query, pairs in groups.items():
        item_scores: dict[str, float] = {}
        item_rel: dict[str, float] = {}

        for rec, pred in pairs:
            a_id = str(rec.get("id", "")) + "_A"
            b_id = str(rec.get("id", "")) + "_B"
            ua = float(rec.get("urgency_a", 0) or 0)
            ub = float(rec.get("urgency_b", 0) or 0)

            if pred == 0:
                item_scores[a_id] = item_scores.get(a_id, 0) + 1
                item_scores[b_id] = item_scores.get(b_id, 0)
            elif pred == 1:
                item_scores[b_id] = item_scores.get(b_id, 0) + 1
                item_scores[a_id] = item_scores.get(a_id, 0)
            else:
                item_scores[a_id] = item_scores.get(a_id, 0) + 0.5
                item_scores[b_id] = item_scores.get(b_id, 0) + 0.5

            item_rel[a_id] = ua
            item_rel[b_id] = ub

        ranked = sorted(item_scores.keys(), key=lambda x: item_scores[x], reverse=True)
        ideal = sorted(item_rel.keys(), key=lambda x: item_rel[x], reverse=True)

        def dcg(items, k=5):
            s = 0.0
            for i, item in enumerate(items[:k], 1):
                rel = item_rel.get(item, 0)
                s += rel / math.log2(i + 1)
            return s

        idcg = dcg(ideal)
        if idcg > 0:
            ndcg_scores.append(dcg(ranked) / idcg)

    return sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0


def per_type_accuracy(records: list[dict], predictions: list[int]) -> dict[str, float]:
    from collections import defaultdict
    buckets: dict[str, list] = defaultdict(list)
    for rec, pred in zip(records, predictions):
        pt = rec.get("pair_type", "unknown")
        label = int(rec.get("preference", -1))
        buckets[pt].append((pred, label))

    result = {}
    for pt, items in buckets.items():
        correct = sum(1 for p, l in items if l != -1 and p == l)
        total = sum(1 for _, l in items if l != -1)
        result[pt] = round(correct / total, 4) if total > 0 else None
    return result


# ── Runner ───────────────────────────────────────────────────────────────────


def run_variant(args) -> None:
    records = [json.loads(l) for l in open(TEST_DATA)]
    labels = [int(r.get("preference", -1)) for r in records]

    if args.variant == "heuristic":
        predictions = [heuristic_predict(r) for r in records]
    else:
        import torch
        from transformers import AutoTokenizer, Gemma4ForCausalLM

        device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"Loading tokenizer from {args.checkpoint} ...")
        tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)

        print(f"Loading model from {args.checkpoint} ...")
        model = Gemma4ForCausalLM.from_pretrained(
            args.checkpoint,
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            device_map="auto",
        )
        model.training = False

        if args.adapter:
            from peft import PeftModel
            print(f"Loading PEFT adapter from {args.adapter} ...")
            model = PeftModel.from_pretrained(model, args.adapter)

        print(f"Scoring {len(records)} pairs ...")
        predictions = []
        for i, rec in enumerate(records):
            prompt = build_prompt(rec)
            pred = model_predict(model, tokenizer, prompt, device)
            predictions.append(pred)
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(records)}")

    acc = pairwise_accuracy(predictions, labels)
    tau = kendall_tau(predictions, labels)
    ndcg5 = ndcg_at_5(records, predictions)
    by_type = per_type_accuracy(records, predictions)
    n_abstain = sum(1 for p in predictions if p == -1)

    result = {
        "variant": args.variant,
        "checkpoint": getattr(args, "checkpoint", None),
        "adapter": getattr(args, "adapter", None),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "n_pairs": len(records),
        "n_abstain": n_abstain,
        "pairwise_accuracy": round(acc, 4),
        "kendall_tau": round(tau, 4),
        "ndcg_at_5": round(ndcg5, 4),
        "by_pair_type": by_type,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"{args.variant}-results.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nVariant: {args.variant}")
    print(f"  Pairwise accuracy: {acc:.4f}")
    print(f"  Kendall's tau:     {tau:.4f}")
    print(f"  NDCG@5:            {ndcg5:.4f}")
    print(f"  By type: {by_type}")
    print(f"Results: {out}")


def run_aggregate() -> None:
    results = []
    for f in sorted(OUTPUT_DIR.glob("*-results.json")):
        if "benchmark_report" not in f.name:
            results.append(json.loads(f.read_text()))

    if not results:
        print("No variant results found. Run each variant first.", file=sys.stderr)
        sys.exit(1)

    ranked = sorted(results, key=lambda r: r["pairwise_accuracy"], reverse=True)
    best = ranked[0]["variant"]

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "test_data": TEST_DATA,
        "n_pairs": results[0]["n_pairs"] if results else 0,
        "best_checkpoint": best,
        "results": {r["variant"]: r for r in results},
        "ranking": [r["variant"] for r in ranked],
    }

    AGGREGATE_REPORT.write_text(json.dumps(report, indent=2))
    print("\n=== BENCHMARK REPORT ===")
    print(f"{'Variant':12s}  {'Acc':6s}  {'Tau':6s}  {'NDCG@5':6s}")
    print("-" * 40)
    for r in ranked:
        print(
            f"{r['variant']:12s}  {r['pairwise_accuracy']:.4f}  "
            f"{r['kendall_tau']:.4f}  {r['ndcg_at_5']:.4f}"
        )
    print(f"\nBest: {best}")
    print(f"Report: {AGGREGATE_REPORT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Score one variant")
    run_p.add_argument("--variant", required=True,
                       choices=["heuristic", "sft", "lora", "qlora", "dpo"])
    run_p.add_argument("--checkpoint", default=None,
                       help="Model checkpoint path (not needed for heuristic)")
    run_p.add_argument("--adapter", default=None,
                       help="PEFT adapter path (for lora/qlora)")

    sub.add_parser("aggregate", help="Aggregate all variant results into final report")

    # Support flat invocation: python run_benchmark.py --variant X
    parser.add_argument("--variant", default=None)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--aggregate", action="store_true")

    args = parser.parse_args()

    if args.aggregate or (hasattr(args, "cmd") and args.cmd == "aggregate"):
        run_aggregate()
    elif args.variant or (hasattr(args, "cmd") and args.cmd == "run"):
        if not args.variant:
            parser.error("--variant required")
        if args.variant != "heuristic" and not args.checkpoint:
            parser.error("--checkpoint required for model variants")
        run_variant(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
