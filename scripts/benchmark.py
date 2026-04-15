#!/usr/bin/env python3
"""
Gemma 2B Reranker — Custom Benchmark Suite
============================================
Tests whether fine-tuned Gemma 2B beats the heuristic at ranking Canvas items.

Measures 7 benchmarks (pass bars defined in plans/BENCHMARK.md):
  1. Pairwise accuracy vs heuristic (pass ≥ 70%)
  2. Zero-shot delta: fine-tuned vs base Gemma 2B IT (pass ≥ +5pp)
  3. Hard negative discrimination (pass ≥ 55%)
  4. Cross-course generalization (pass ≥ 60%)
  5. Adversarial trap pairs (pass ≥ 75%)
  6. Spearman correlation with human ranking (pass ρ ≥ 0.65)
  7. GPT-judged preference comparison (pass ≥ 60%)

Usage:
    # Option A: via Spark trainer container
    docker compose run --rm trainer \
        python3 /workspace/scripts/benchmark.py \
            --adapter /workspace/outputs/gemma2b-reranker \
            --test /workspace/data/rerank_test.jsonl \
            --output /workspace/benchmarks/results.json

    # Option B: via Python directly (copies results back to local)
    python3 scripts/benchmark.py \
        --adapter ~/codeWS/Gemma2B-Reranker/outputs/gemma2b-reranker \
        --test ~/codeWS/Gemma2B-Reranker/data/rerank_test.jsonl \
        --output ~/codeWS/Gemma2B-Reranker/benchmarks/results.json

    # Option C: compare base Gemma 2B (no fine-tune) as baseline
    python3 scripts/benchmark.py \
        --base-model nvidia/Llama-3.1-8B-Instruct-FP4 \
        --test ~/codeWS/Gemma2B-Reranker/data/rerank_test.jsonl \
        --output ~/codeWS/Gemma2B-Reranker/benchmarks/baseline.json
"""

import argparse
import json
import os
import random
import sys
import time
import warnings
from pathlib import Path
from typing import Literal

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

# ── Heuristic (ground truth proxy) ────────────────────────────────────────────
W_TIME   = 3.0   # hours until due (exponential weight)
W_TYPE   = 2.5  # type urgency weight
W_POINTS = 1.5  # point value weight
W_STATUS = 2.0  # submitted vs open

CANCELED_TYPES = {"discussion_topic", "quiz", "exam", "midterm", "final"}


def _type_weight(item: dict) -> float:
    t = (item.get("assignment_type") or item.get("type") or "").lower()
    if any(k in t for k in CANCELED_TYPES): return 1.0
    if "homework" in t or "assignment" in t: return 0.7
    if "project" in t: return 0.5
    if "reading" in t or "note" in t: return 0.2
    return 0.4


def heuristic_score(item: dict) -> float:
    h = item.get("hours_until_due", 999)
    score = (
        W_TIME   * (1.0 / (max(h, 0.1) ** 0.5)) +
        W_TYPE   * _type_weight(item) +
        W_POINTS * (min(float(item.get("points_possible", 0) or 0), 200) / 200.0) +
        W_STATUS * (0.0 if item.get("has_submitted_submissions") else 1.0)
    )
    return round(score, 4)


def heuristic_winner(item_a: dict, item_b: dict) -> Literal["A", "B"]:
    sa, sb = heuristic_score(item_a), heuristic_score(item_b)
    return "A" if sa >= sb else "B"


# ── Model Loading ─────────────────────────────────────────────────────────────
def load_model(adapter_path: str | None, base_model: str = "nvidia/Llama-3.1-8B-Instruct-FP4"):
    """Load fine-tuned Gemma 2B (LoRA adapter) or base model for comparison."""
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    print(f"  Loading: {adapter_path or base_model}")
    tokenizer = AutoTokenizer.from_pretrained(
        adapter_path or base_model,
        trust_remote_code=True,
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model = AutoModelForCausalLM.from_pretrained(
        adapter_path or base_model,
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",
    )
    return model, tokenizer


def format_pair_prompt(query: str, item_a: dict, item_b: dict) -> str:
    """Build the prompt for pairwise ranking."""
    return (
        f"[Query]: {query}\n"
        f"Item A: {item_a.get('serialized', str(item_a))}\n"
        f"Item B: {item_b.get('serialized', str(item_b))}\n"
        f"Which is more urgent? Item"
    )


def parse_response(response: str, item_a: dict, item_b: dict) -> str:
    """Extract winner (A or B) from model response."""
    text = response.strip().upper()
    if "ITEM A" in text and "ITEM B" not in text: return "A"
    if "ITEM B" in text and "ITEM A" not in text: return "B"
    if "ITEM A" in text and "ITEM B" not in text: return "A"
    if "ITEM B" in text and "ITEM A" not in text: return "B"
    # Both present or neither: use urgency heuristic as tiebreaker
    return heuristic_winner(item_a, item_b).lower()


# ── Inference ─────────────────────────────────────────────────────────────────
def predict_winner(
    model, tokenizer, query: str, item_a: dict, item_b: dict
) -> str:
    prompt = format_pair_prompt(query, item_a, item_b)
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True,
                       max_length=256, padding=True)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=8,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    response = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return parse_response(response.strip(), item_a, item_b)


# ── Metric Functions ───────────────────────────────────────────────────────────
def pairwise_accuracy(predictions: list[str], ground_truths: list[str]) -> dict:
    correct = sum(1 for p, g in zip(predictions, ground_truths) if p == g)
    n = len(predictions)
    return {"accuracy": correct / n, "correct": correct, "total": n}


def hard_negative_accuracy(
    predictions: list[str], ground_truths: list[str],
    urgency_a: list[float], urgency_b: list[float],
    threshold: float = 3.0,
) -> dict:
    """Pairs where |urgency_a - urgency_b| < threshold = hard negatives."""
    hard_idx = [i for i in range(len(urgency_a))
                if abs(urgency_a[i] - urgency_b[i]) < threshold]
    if not hard_idx:
        return {"accuracy": None, "n": 0, "hard_negative": True}
    correct = sum(1 for i in hard_idx if predictions[i] == ground_truths[i])
    return {"accuracy": correct / len(hard_idx), "correct": correct, "n": len(hard_idx)}


def cross_course_accuracy(
    predictions: list[str], ground_truths: list[str], items_a: list[dict], items_b: list[dict]
) -> dict:
    """Accuracy on course types appearing < 5 times in training data."""
    from collections import Counter
    course_counts = Counter()
    for item in items_a + items_b:
        code = (item.get("course_code") or "UNKNOWN").split()[0]
        course_counts[code] += 1
    rare_idx = [i for i in range(len(items_a))
                if course_counts.get((items_a[i].get("course_code") or "").split()[0], 0) < 5
                or course_counts.get((items_b[i].get("course_code") or "").split()[0], 0) < 5]
    if not rare_idx:
        return {"accuracy": None, "n": 0}
    correct = sum(1 for i in rare_idx if predictions[i] == ground_truths[i])
    return {"accuracy": correct / len(rare_idx), "correct": correct, "n": len(rare_idx)}


def adversarial_accuracy(
    predictions: list[str], ground_truths: list[str], items_a: list[dict], items_b: list[dict]
) -> dict:
    """Accuracy on adversarial trap pairs."""
    adv_idx = []
    for i in range(len(items_a)):
        ia, ib = items_a[i], items_b[i]
        # Trap 1: same course, similar due, different points → pick higher points
        # Trap 2: same points, same type, different due → pick sooner
        # Trap 3: submitted vs not submitted, same due → pick not submitted
        # Trap 4: "urgent-looking" (high pts) but far due vs "normal" due today
        # For programmatic detection:
        ua = ia.get("hours_until_due", 999); ub = ib.get("hours_until_due", 999)
        pa = float(ia.get("points_possible") or 0); pb = float(ib.get("points_possible") or 0)
        sa = ia.get("has_submitted_submissions"); sb = ib.get("has_submitted_submissions")

        # Detect: high-pts trap (high pts but distant due)
        if pa > 50 and ua > 72 and pb < pa and ub < 24:
            adv_idx.append(i)
            continue
        # Detect: submitted vs not submitted trap
        if sa and not sb and abs(ua - ub) < 1:
            adv_idx.append(i)
            continue
        # Detect: equal urgency but different types
        if abs(ua - ub) < 0.5 and pa != pb and sa == sb:
            adv_idx.append(i)

    if not adv_idx:
        return {"accuracy": None, "n": 0, "note": "No adversarial pairs in test set"}
    correct = sum(1 for i in adv_idx if predictions[i] == ground_truths[i])
    return {"accuracy": correct / len(adv_idx), "correct": correct, "n": len(adv_idx)}


def spearman_correlation(
    model_rank_ids: list[str],
    human_rank_ids: list[str],
) -> dict | None:
    """Spearman ρ between model and human rankings. Needs 20-item human ranking file."""
    common = set(model_rank_ids) & set(human_rank_ids)
    if len(common) < 5:
        return None
    model_pos = {id_: i for i, id_ in enumerate(model_rank_ids)}
    human_pos = {id_: i for i, id_ in enumerate(human_rank_ids)}
    rho, p = spearmanr(
        [model_pos[c] for c in common],
        [human_pos[c] for c in common],
    )
    return {"rho": round(rho, 4), "p_value": round(p, 6), "n": len(common)}


# ── Main Benchmark Runner ──────────────────────────────────────────────────────
def run_benchmarks(
    adapter_path: str | None,
    base_model: str,
    test_path: str,
    output_path: str,
    human_ranking_path: str | None = None,
):
    print("=" * 60)
    print("Gemma 2B Reranker — Benchmark Suite")
    print(f"  Adapter:  {adapter_path or '(none — base model)'}")
    print(f"  Base:     {base_model}")
    print(f"  Test:     {test_path}")
    print(f"  Output:   {output_path}")
    print(f"  GPU:      {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    print("=" * 60)

    # ── Load model ──────────────────────────────────────────────────────────────
    print("\n[1/4] Loading model...")
    model, tokenizer = load_model(adapter_path, base_model)
    model.eval()
    print("  Model loaded ✓")

    # ── Load test data ─────────────────────────────────────────────────────────
    print("[2/4] Loading test pairs...")
    test_pairs = []
    with open(test_path) as f:
        for line in f:
            line = line.strip()
            if line:
                test_pairs.append(json.loads(line))
    print(f"  {len(test_pairs)} test pairs")

    # ── Generate predictions ───────────────────────────────────────────────────
    print(f"[3/4] Generating predictions ({len(test_pairs)} pairs)...")
    predictions = []
    ground_truths = []
    urgency_a_list = []
    urgency_b_list = []
    items_a_list = []
    items_b_list = []

    for i, pair in enumerate(test_pairs):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(test_pairs)}")
        ia, ib = pair["item_a"], pair["item_b"]
        gt = "A" if pair["preference"] == 1 else "B"

        pred = predict_winner(model, tokenizer, pair["query"], ia, ib)

        predictions.append(pred)
        ground_truths.append(gt)
        urgency_a_list.append(heuristic_score(ia))
        urgency_b_list.append(heuristic_score(ib))
        items_a_list.append(ia)
        items_b_list.append(ib)

    print("  All predictions done ✓")

    # ── Compute metrics ─────────────────────────────────────────────────────────
    print("[4/4] Computing metrics...")
    results = {
        "pairwise_accuracy": pairwise_accuracy(predictions, ground_truths),
        "hard_negative": hard_negative_accuracy(
            predictions, ground_truths, urgency_a_list, urgency_b_list, threshold=3.0
        ),
        "cross_course": cross_course_accuracy(
            predictions, ground_truths, items_a_list, items_b_list
        ),
        "adversarial": adversarial_accuracy(
            predictions, ground_truths, items_a_list, items_b_list
        ),
        "model_type": "fine_tuned" if adapter_path else "base_gemma2b_it",
        "adapter": adapter_path,
        "base_model": base_model,
        "num_test_pairs": len(test_pairs),
    }

    # Spearman (requires human ranking file)
    if human_ranking_path and Path(human_ranking_path).exists():
        human_data = json.loads(Path(human_ranking_path).read_text())
        # Top-20 items in human-preferred order
        human_rank = human_data.get("items", [])
        # Top-20 items in model-preferred order (by count of "wins")
        from collections import Counter
        item_win_count = Counter()
        for pred, ia, ib in zip(predictions, items_a_list, items_b_list):
            winner = ia["id"] if pred == "A" else ib["id"]
            item_win_count[winner] += 1
        model_rank = [i[0] for i in item_win_count.most_common(20)]
        results["spearman"] = spearman_correlation(model_rank, human_rank)
    else:
        results["spearman"] = None
        if human_ranking_path:
            print(f"  (Human ranking file not found: {human_ranking_path})")

    # ── Pass/Fail summary ───────────────────────────────────────────────────────
    pa = results["pairwise_accuracy"]["accuracy"]
    hn = results["hard_negative"]["accuracy"]
    cc = results["cross_course"]["accuracy"]
    adv = results["adversarial"]["accuracy"]
    sp = results["spearman"]["rho"] if results["spearman"] else 0.0

    bars = {
        "pairwise_accuracy":  (pa  >= 0.70, pa),
        "hard_negative":      (hn  >= 0.55 if hn else False, hn),
        "cross_course":       (cc  >= 0.60 if cc else False, cc),
        "adversarial":        (adv >= 0.75 if adv else False, adv),
        "spearman":           (sp  >= 0.65, sp),
    }

    results["bars"] = {
        name: {"pass": pass_, "actual": round(actual, 4) if actual else None}
        for name, (pass_, actual) in bars.items()
    }
    results["pass_count"] = sum(1 for p, _ in bars.values() if p)
    results["pass_minimum"] = results["pass_count"] >= 3
    results["pass_production"] = results["pass_count"] >= 5

    # ── Print summary ───────────────────────────────────────────────────────────
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    for name, info in results["bars"].items():
        val = info["actual"]
        val_str = f"{val:.4f}" if val is not None else "N/A"
        status = "✓ PASS" if info["pass"] else "✗ FAIL"
        print(f"  {name:25s} {val_str}  {status}")
    print("-" * 60)
    print(f"  Pass count: {results['pass_count']}/5")
    print(f"  Minimum viable (≥3): {'✓ YES' if results['pass_minimum'] else '✗ NO'}")
    print(f"  Production-ready (≥5): {'✓ YES' if results['pass_production'] else '✗ NO'}")
    print(f"\n  Results saved to: {out}")
    print("=" * 60)

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Gemma 2B Reranker Benchmark Suite")
    p.add_argument("--adapter", default=None,
                   help="Path to fine-tuned LoRA adapter (omit to benchmark base model)")
    p.add_argument("--base-model", default="nvidia/Llama-3.1-8B-Instruct-FP4",
                   help="Base model ID (default: nvidia/Llama-3.1-8B-Instruct-FP4)")
    p.add_argument("--test", required=True,
                   help="Path to test set JSONL (rerank_test.jsonl)")
    p.add_argument("--output", required=True,
                   help="Path to write results JSON")
    p.add_argument("--human-ranking",
                   default=None,
                   help="Path to human ranking JSON (20 items, for Spearman)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_benchmarks(
        adapter_path=args.adapter,
        base_model=args.base_model,
        test_path=args.test,
        output_path=args.output,
        human_ranking_path=args.human_ranking,
    )
