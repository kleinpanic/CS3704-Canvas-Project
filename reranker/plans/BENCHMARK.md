# Gemma 2B Reranker — Custom Benchmark Spec

## Why Standard Benchmarks Don't Apply

Standard LLM benchmarks (MMLU, HellaSwag, GSM8K, etc.) measure general knowledge and reasoning. They tell us Gemma 2B is a capable language model, but **nothing about whether our fine-tuned reranker is actually better at Canvas priority ranking than the heuristic**.

We need a custom benchmark that validates our specific premise:
> *"A fine-tuned Gemma 2B ranks Canvas items by priority more accurately than a simple heuristic formula."*

---

## The Benchmark Pipeline

```
Full dataset (2000 pairs)
        ↓  stratified split
train (1800) / test (200) ← never seen during training
        ↓
Heuristic wins on test set (baseline accuracy)
Gemma 2B IT zero-shot on test set (GPT-graded)
Gemma 2B fine-tuned on test set
        ↓
compare: fine-tuned > heuristic? by how much?
```

---

## Benchmark 1: Pairwise Accuracy on Held-Out Test Set

**What it measures**: % of test pairs where model's preference agrees with heuristic's preference.

**Method**:
1. Hold out 10% of pairs (stratified by pair type) as test set — NEVER seen during training
2. Run fine-tuned model on each test pair, extract predicted winner (A or B)
3. Compare to heuristic winner (urgency_a vs urgency_b)
4. Report accuracy

**Pass criterion**: Fine-tuned > 70% agreement with heuristic on held-out pairs

**Why this matters**: If the model can't at least match the heuristic on training data distribution, the fine-tuning didn't work.

---

## Benchmark 2: Zero-Shot vs Fine-Tuned Delta

**What it measures**: How much does fine-tuning improve over base Gemma 2B IT?

**Method**:
1. Run base `google/gemma-2b-it` (zero-shot, no fine-tuning) on test set
2. Run fine-tuned model on same test set
3. Compare accuracy

**Pass criterion**: Fine-tuned > zero-shot by ≥ 5 percentage points

**Why this matters**: If fine-tuning provides < 5pt improvement, the model was already capable enough without fine-tuning — or the training signal was too weak.

---

## Benchmark 3: Hard Negative Discrimination

**What it measures**: Can the model correctly rank pairs where the heuristic is uncertain (urgency diff < 3.0)?

**Method**:
1. Filter test set to only hard negatives (urgency diff < 3.0)
2. Run fine-tuned model on these pairs
3. These are the cases where the heuristic is genuinely ambiguous

**Pass criterion**: Fine-tuned ≥ 55% accuracy on hard negatives

**Why this matters**: Hard negatives are exactly where a learned model should beat a fixed formula. 55% (just above random) is the minimum bar — passing means the model learned *something* beyond the heuristic.

---

## Benchmark 4: Cross-Course Generalization

**What it measures**: Does the model generalize to course types it rarely saw in training?

**Method**:
1. Identify course pairs that appear infrequently in training data
2. Create a held-out "rare course" test set
3. Test whether model correctly ranks these

**Pass criterion**: ≥ 60% accuracy on rare-course subset

**Why this matters**: If the model only works for CS 3704 (most common in training data) but fails for HD 3114, it memorized, not learned urgency.

---

## Benchmark 5: Adversarial Pairs

**What it measures**: Can the model resist simple shortcuts?

**Pairs to test**:
1. Same course, similar due dates, different point values → should pick higher points
2. Same points, same type, different due dates → should pick sooner
3. Submitted vs not submitted with same due → should pick not submitted
4. "Trap" pairs: looks urgent (high points) but actually distant vs (low points) due today

**Pass criterion**: ≥ 75% on adversarial set

**Why this matters**: Tests whether the model learned composite urgency or just copied single heuristics.

---

## Benchmark 6: Qualitative Human Review

**What it measures**: Do the model's ranked lists make sense to a human?

**Method**:
1. Take 20 random held-out items from Klein's current Canvas
2. Ask Gemma to rank them by urgency (1-20)
3. Ask Klein to rank the same 20 items (independent)
4. Compare Spearman correlation between model ranking and human ranking

**Pass criterion**: Spearman ρ ≥ 0.65

**Why this matters**: Accuracy metrics miss whether the output *feels* right. The model's job is to surface what Klein would actually prioritize.

---

## Benchmark 7: GPT-Judged Preference

**What it measures**: When the model disagrees with the heuristic, who is more reasonable?

**Method**:
1. Run fine-tuned model on test set
2. For pairs where model ≠ heuristic:
   - Prompt GPT-4o (or local Nemotron) with both item descriptions + reason
   - Ask: "Which item is more urgent for a student? Consider: due date, type, points, status."
3. Compare GPT's judgment to both model and heuristic

**Pass criterion**: Model's judgment ≥ GPT's judgment ≥ heuristic's judgment (model should be closest to GPT on average)

**Why this matters**: The heuristic is our ground truth proxy, but it's imperfect. GPT-4o provides an independent reasoning pass — if the fine-tuned model disagrees with both the heuristic and GPT, that's interesting. If it agrees with GPT over the heuristic, that's validation of learned reasoning.

---

## Summary Metrics Table

| Benchmark | Metric | Pass Bar | Fail Bar |
|-----------|--------|----------|----------|
| Pairwise Accuracy | % agreement w/ heuristic | ≥ 70% | < 60% |
| Zero-Shot Delta | fine-tuned - zero-shot | ≥ +5pp | ≤ 0pp |
| Hard Negative | % accuracy | ≥ 55% | < 50% |
| Cross-Course Gen | % accuracy on rare courses | ≥ 60% | < 50% |
| Adversarial | % on trap pairs | ≥ 75% | < 60% |
| Human Correlation | Spearman ρ | ≥ 0.65 | < 0.50 |
| GPT Judgment | Model closer to GPT than heuristic | ≥ 60% | < 50% |

**Overall**: Pass ≥ 5/7 benchmarks = production-ready  
**Minimum viable**: Pass ≥ 3/7 benchmarks

---

## Benchmark Script

```python
# scripts/benchmark.py
"""
Custom Canvas Priority Reranker Benchmark Suite

Tests whether fine-tuned Gemma 2B is better than the heuristic
at ranking Canvas items by priority.

Usage:
    python3 scripts/benchmark.py \\
        --adapter outputs/gemma2b-reranker \\
        --test data/collab/rerank_test.jsonl \\
        --output benchmarks/results.json
"""

import argparse
import json
import random
import statistics
from pathlib import Path
from typing import Literal

from scipy.stats import spearmanr

# ── Heuristic (ground truth proxy) ─────────────────────────────────────────────
W_TIME = 3.0; W_TYPE = 2.5; W_POINTS = 1.5; W_STATUS = 2.0

def heuristic_score(item: dict) -> float:
    # ... (same formula as collect_rerank_dataset.py)

def heuristic_winner(item_a: dict, item_b: dict) -> Literal["A", "B"]:
    sa, sb = heuristic_score(item_a), heuristic_score(item_b)
    return "A" if sa >= sb else "B"

# ── Metric functions ───────────────────────────────────────────────────────────

def pairwise_accuracy(model_outputs: list[dict], heuristic_fn) -> dict:
    """
    For each dict: {"item_a": {...}, "item_b": {...}, "predicted": "A"|"B", "ground_truth": "A"|"B"}
    """
    correct = sum(1 for o in model_outputs if o["predicted"] == o["ground_truth"])
    return {"accuracy": correct/len(model_outputs), "n": len(model_outputs)}


def hard_negative_accuracy(model_outputs: list[dict],
                           urgency_a: list[float],
                           urgency_b: list[float]) -> dict:
    """
    Filter to pairs where |urgency_a - urgency_b| < 3.0 (hard negatives).
    """
    hard = [o for o, ua, ub in zip(model_outputs, urgency_a, urgency_b)
            if abs(ua - ub) < 3.0]
    correct = sum(1 for o in hard if o["predicted"] == o["ground_truth"])
    return {"accuracy": correct/len(hard), "n": len(hard), "hard_negative": True}


def adversarial_accuracy(model_outputs: list[dict],
                       adversarial_mask: list[bool]) -> dict:
    adv = [o for o, m in zip(model_outputs, adversarial_mask) if m]
    correct = sum(1 for o in adv if o["predicted"] == o["ground_truth"])
    return {"accuracy": correct/len(adv), "n": len(adv)}


def spearman_correlation(model_ranking: list[str],  # item_ids ordered by model
                         human_ranking: list[str]) -> float:  # item_ids ordered by human
    """Spearman rank correlation between model and human rankings."""
    # Convert to ranks
    model_rank = {item: i for i, item in enumerate(model_ranking)}
    human_rank = {item: i for i, item in enumerate(human_ranking)}
    items = list(set(model_rank) & set(human_rank))
    rho, _ = spearmanr([model_rank[i] for i in items], [human_rank[i] for i in items])
    return rho


# ── Main benchmark runner ───────────────────────────────────────────────────────

def run_benchmarks(adapter_path: Path,
                  test_pairs: list[dict],
                  output_path: Path):
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    import torch

    # Load fine-tuned model
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(
        adapter_path, quantization_config=bnb, device_map={"": 0}
    )
    tokenizer = AutoTokenizer.from_pretrained(adapter_path)

    # Generate predictions
    outputs = []
    for pair in test_pairs:
        prompt = format_prompt(pair)  # same format as SFTTrainer
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=256).to("cuda")
        out = model.generate(**inputs, max_new_tokens=32, do_sample=False)
        response = tokenizer.decode(out[0], skip_special_tokens=True)
        predicted = parse_response(response)  # extract "A" or "B"

        ground_truth = "A" if pair["preference"] == 1 else "B"
        outputs.append({
            "predicted": predicted,
            "ground_truth": ground_truth,
            "pair_id": pair["id"],
            "pair_type": pair.get("pair_type", "unknown"),
            "item_a": pair["item_a"],
            "item_b": pair["item_b"],
        })

    # ── Run all benchmarks ─────────────────────────────────────────────────
    results = {}

    # 1. Pairwise accuracy
    results["pairwise_accuracy"] = pairwise_accuracy(outputs, heuristic_winner)

    # 2. Hard negatives
    ua = [o["item_a"]["urgency"] for o in outputs]
    ub = [o["item_b"]["urgency"] for o in outputs]
    results["hard_negative"] = hard_negative_accuracy(outputs, ua, ub)

    # 3. Adversarial
    adv_mask = [detect_adversarial(o) for o in test_pairs]
    results["adversarial"] = adversarial_accuracy(outputs, adv_mask)

    # 4. Cross-course (courses appearing < 5 times in training)
    rare_mask = [is_rare_course(o["item_a"]) or is_rare_course(o["item_b"])
                  for o in outputs]
    rare = [o for o, m in zip(outputs, rare_mask) if m]
    rare_correct = sum(1 for o in rare if o["predicted"] == o["ground_truth"])
    results["cross_course"] = {
        "accuracy": rare_correct/len(rare) if rare else None,
        "n": len(rare)
    }

    # 5. Spearman (if human ranking provided)
    if (human_ranking_path := output_path.parent / "human_ranking.json").exists():
        human_rank = json.loads(human_ranking_path.read_text())
        # Get model's ranking of those 20 items
        model_items = [o["item_a"]["id"] for o in outputs[:20]]  # top 20 by model
        rho = spearman_correlation(model_items, human_rank["items"])
        results["spearman"] = {"rho": rho}

    # 6. Zero-shot delta
    # (Run base model on same test set, compare to fine-tuned)
    results["zero_shot_delta"] = run_zero_shot_baseline(test_pairs)

    # ── Summary ───────────────────────────────────────────────────────────────
    results["summary"] = {
        "pass_5_of_7": sum([
            results["pairwise_accuracy"]["accuracy"] >= 0.70,
            results["hard_negative"]["accuracy"] >= 0.55,
            results["adversarial"]["accuracy"] >= 0.75,
            results.get("spearman", {}).get("rho", 0) >= 0.65,
            results["zero_shot_delta"]["delta_pp"] >= 5.0,
            results["cross_course"]["accuracy"] >= 0.60,
        ]) >= 5,
        "pass_minimum": sum([
            results["pairwise_accuracy"]["accuracy"] >= 0.70,
            results["hard_negative"]["accuracy"] >= 0.55,
        ]) >= 1,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return results
```
