"""
validate_dpo_holdout.py — held-out validation of DPO v3 vs the merged BF16
reference, on data/dpo_test_v3.jsonl (item-disjoint from training, per
source/split_dpo_holdout.py).

Two complementary measurements:

  1. Logprob-delta improvement (the same metric validate_dpo.py used for
     v2, but on actually-held-out data this time): for each test pair,
     compare delta_v3 = logprob_v3(chosen) - logprob_v3(rejected) against
     delta_ref = logprob_ref(chosen) - logprob_ref(rejected). DPO wins
     when delta_v3 > delta_ref.

  2. Pairwise prediction accuracy via training-prompt-format generation:
     feed the trained prompt template "Which Canvas item is more urgent
     and why?\n\n[Query]: {q}\nItem A: {a}\nItem B: {b}", greedy-decode
     the response, scan for the first occurrence of "Item A" or "Item B"
     and compare to which the chosen response argues for.

Both measurements report point estimates plus Wilson 95% confidence
intervals — directly addressing the audit P2 finding that v2 reported
no uncertainty quantification.

Outputs checkpoints/dpo-v3-checkpoint/holdout_validation.json.
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

DPO_CHECKPOINT = "./checkpoints/dpo-v3-checkpoint"
REF_CHECKPOINT = "./checkpoints/gguf/merged_bf16"
TEST_PATH = "./data/dpo_test_v3.jsonl"
REPORT_PATH = Path(DPO_CHECKPOINT) / "holdout_validation.json"


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    halfwidth = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - halfwidth), min(1.0, center + halfwidth))


def chosen_picks(chosen_text: str) -> str | None:
    m = re.search(r"\bItem\s*([AB])\b", chosen_text)
    return m.group(1).upper() if m else None


def sequence_log_prob(model, tokenizer, prompt: str, completion: str) -> float:
    import torch
    full = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt},
         {"role": "assistant", "content": completion}],
        tokenize=False,
        add_generation_prompt=False,
    )
    enc = tokenizer(full, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model(**enc, labels=enc["input_ids"])
    return -out.loss.item() * enc["input_ids"].shape[1]


def generate_prediction(model, tokenizer, prompt: str, max_new_tokens: int = 32) -> str:
    """
    Greedy-decode a response in the SAME chat-template format that
    sequence_log_prob uses, so the two metrics measure under the same
    serialization regime (audit follow-up: codex + gemini both flagged the
    raw-prompt-vs-chat-template inconsistency in the original v3 run).
    """
    import torch
    chat_prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False,
        add_generation_prompt=True,
    )
    enc = tokenizer(chat_prompt, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(
            **enc,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    n_prompt = enc["input_ids"].shape[1]
    return tokenizer.decode(out[0][n_prompt:], skip_special_tokens=True)


def binomial_p_one_sided(k: int, n: int, p: float) -> float:
    from math import comb
    return round(sum(comb(n, i) * p**i * (1-p)**(n-i) for i in range(k, n + 1)), 6)


def main():
    import torch
    from transformers import AutoTokenizer, Gemma4ForCausalLM

    print("=" * 70)
    print("DPO v3 HELD-OUT VALIDATION")
    print(f"  test:       {TEST_PATH}")
    print(f"  v3 ckpt:    {DPO_CHECKPOINT}")
    print(f"  ref ckpt:   {REF_CHECKPOINT}")
    print("=" * 70)

    pairs = [json.loads(l) for l in open(TEST_PATH) if l.strip()]
    print(f"\n[load] {len(pairs)} held-out pairs from {TEST_PATH}")

    print(f"\n[load] DPO v3 model {DPO_CHECKPOINT} ...")
    dpo = Gemma4ForCausalLM.from_pretrained(
        DPO_CHECKPOINT, torch_dtype=torch.bfloat16, attn_implementation="sdpa", device_map="auto",
    )
    dpo.train(False)

    print(f"[load] reference model {REF_CHECKPOINT} ...")
    ref = Gemma4ForCausalLM.from_pretrained(
        REF_CHECKPOINT, torch_dtype=torch.bfloat16, attn_implementation="sdpa", device_map="auto",
    )
    ref.train(False)

    tokenizer = AutoTokenizer.from_pretrained(DPO_CHECKPOINT)

    n_improved = 0
    n_pairwise_correct_dpo = 0
    n_pairwise_correct_ref = 0
    n_dpo_abstain = 0
    n_ref_abstain = 0
    detailed = []

    for i, pair in enumerate(pairs):
        prompt = pair["prompt"]
        chosen = pair["chosen"]
        rejected = pair["rejected"]
        gold = chosen_picks(chosen)

        ref_chosen = sequence_log_prob(ref, tokenizer, prompt, chosen)
        ref_rejected = sequence_log_prob(ref, tokenizer, prompt, rejected)
        dpo_chosen = sequence_log_prob(dpo, tokenizer, prompt, chosen)
        dpo_rejected = sequence_log_prob(dpo, tokenizer, prompt, rejected)
        ref_delta = ref_chosen - ref_rejected
        dpo_delta = dpo_chosen - dpo_rejected
        improvement = dpo_delta - ref_delta
        improved = improvement > 0
        if improved:
            n_improved += 1

        ref_pred = chosen_picks(generate_prediction(ref, tokenizer, prompt))
        dpo_pred = chosen_picks(generate_prediction(dpo, tokenizer, prompt))
        if dpo_pred is None:
            n_dpo_abstain += 1
        elif dpo_pred == gold:
            n_pairwise_correct_dpo += 1
        if ref_pred is None:
            n_ref_abstain += 1
        elif ref_pred == gold:
            n_pairwise_correct_ref += 1

        detailed.append({
            "pair": i + 1,
            "gold": gold,
            "ref_pred": ref_pred,
            "dpo_pred": dpo_pred,
            "ref_delta": round(ref_delta, 4),
            "dpo_delta": round(dpo_delta, 4),
            "improvement": round(improvement, 4),
            "improved": improved,
        })

        if (i + 1) % 25 == 0:
            print(f"  [{i+1:3d}/{len(pairs)}] improved={n_improved} "
                  f"dpo_acc={n_pairwise_correct_dpo}/{i+1-n_dpo_abstain}  "
                  f"ref_acc={n_pairwise_correct_ref}/{i+1-n_ref_abstain}")

    n = len(pairs)
    n_dpo_scored = n - n_dpo_abstain
    n_ref_scored = n - n_ref_abstain

    impr_lo, impr_hi = wilson_ci(n_improved, n)
    dpo_acc = n_pairwise_correct_dpo / n_dpo_scored if n_dpo_scored else 0.0
    dpo_lo, dpo_hi = wilson_ci(n_pairwise_correct_dpo, n_dpo_scored)
    ref_acc = n_pairwise_correct_ref / n_ref_scored if n_ref_scored else 0.0
    ref_lo, ref_hi = wilson_ci(n_pairwise_correct_ref, n_ref_scored)

    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "test_data": TEST_PATH,
        "n_test_pairs": n,
        "logprob_delta": {
            "n_improved": n_improved,
            "rate": round(n_improved / n, 4),
            "wilson_95ci": [round(impr_lo, 4), round(impr_hi, 4)],
            "binomial_p_one_sided": binomial_p_one_sided(n_improved, n, 0.5),
        },
        "pairwise_prediction": {
            "dpo_correct": n_pairwise_correct_dpo,
            "dpo_scored": n_dpo_scored,
            "dpo_abstain": n_dpo_abstain,
            "dpo_accuracy": round(dpo_acc, 4),
            "dpo_wilson_95ci": [round(dpo_lo, 4), round(dpo_hi, 4)],
            "ref_correct": n_pairwise_correct_ref,
            "ref_scored": n_ref_scored,
            "ref_abstain": n_ref_abstain,
            "ref_accuracy": round(ref_acc, 4),
            "ref_wilson_95ci": [round(ref_lo, 4), round(ref_hi, 4)],
        },
        "verdict_threshold": "DPO logprob improvement on > 50% of held-out pairs (lower CI bound > 0.5)",
        "verdict": "PASS" if impr_lo > 0.5 else ("INCONCLUSIVE" if n_improved / n > 0.5 else "FAIL"),
        "pairs": detailed,
    }
    REPORT_PATH.write_text(json.dumps(summary, indent=2))
    print(f"\n{'='*70}")
    print(f"  HELD-OUT RESULTS  (n={n})")
    print(f"{'='*70}")
    print(f"  Logprob improvement:  {n_improved}/{n}  ({n_improved/n*100:.1f}%)  "
          f"[95% CI: {impr_lo*100:.1f}%, {impr_hi*100:.1f}%]")
    print(f"  DPO pairwise acc:     {n_pairwise_correct_dpo}/{n_dpo_scored}  ({dpo_acc*100:.1f}%)  "
          f"[95% CI: {dpo_lo*100:.1f}%, {dpo_hi*100:.1f}%]")
    print(f"  Ref pairwise acc:     {n_pairwise_correct_ref}/{n_ref_scored}  ({ref_acc*100:.1f}%)  "
          f"[95% CI: {ref_lo*100:.1f}%, {ref_hi*100:.1f}%]")
    print(f"  Verdict:              {summary['verdict']}")
    print(f"  Report:               {REPORT_PATH}")


if __name__ == "__main__":
    main()
