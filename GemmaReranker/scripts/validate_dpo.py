"""
DPO Post-Training Validation (Plan 04-03)

Measures whether the DPO policy moved toward chosen responses relative to the SFT
baseline. Computes log-prob deltas for 10 sampled pairs and writes validation_report.json.

Pass criterion: dpo_delta > sft_delta on >= 7 of 10 pairs.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from datetime import datetime

DPO_CHECKPOINT = os.environ.get("DPO_CHECKPOINT", "./checkpoints/dpo-checkpoint")
SFT_CHECKPOINT = os.environ.get("DPO_SFT_CHECKPOINT", "./checkpoints/sft-checkpoint")
DATA_PATH = os.environ.get("VALIDATE_DATA", "./data/dpo_train.jsonl")
REPORT_PATH = pathlib.Path(DPO_CHECKPOINT) / "validation_report.json"
PASS_THRESHOLD = 7


def load_validation_pairs(data_path: str, n: int = 10) -> list[dict]:
    records = [json.loads(l) for l in open(data_path)]
    hard = [r for r in records if r.get("pair_type") == "hard_negative"][:5]
    standard = [r for r in records if r.get("pair_type") != "hard_negative"][:5]
    pairs = (hard + standard)[:n]
    if len(pairs) < n:
        pairs = records[:n]
    return pairs


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


def main():
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, Gemma4ForCausalLM

    print("=" * 64)
    print("DPO VALIDATION — Plan 04-03")
    print("=" * 64)

    # D-12 config check — gemma4_text is the actual model type for the text tower
    cfg = AutoConfig.from_pretrained(DPO_CHECKPOINT)
    assert cfg.model_type in ("gemma4", "gemma4_text"), \
        f"Expected gemma4/gemma4_text, got {cfg.model_type}"
    print(f"[PASS] DPO config OK: model_type={cfg.model_type}")

    # D-12 meta-device probe (no weights allocated)
    _ = AutoModelForCausalLM.from_pretrained(DPO_CHECKPOINT, device_map="meta")
    print("[D-12 PASS] AutoModelForCausalLM meta-device load OK")
    del _

    print(f"\nLoading DPO model from {DPO_CHECKPOINT} ...")
    dpo_model = Gemma4ForCausalLM.from_pretrained(
        DPO_CHECKPOINT,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
        device_map="auto",
    )
    dpo_model.training = False

    print(f"Loading SFT model from {SFT_CHECKPOINT} ...")
    sft_model = Gemma4ForCausalLM.from_pretrained(
        SFT_CHECKPOINT,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
        device_map="auto",
    )
    sft_model.training = False

    tokenizer = AutoTokenizer.from_pretrained(DPO_CHECKPOINT)

    pairs = load_validation_pairs(DATA_PATH)
    print(f"\nEvaluating {len(pairs)} pairs from {DATA_PATH}\n")

    pair_results = []
    n_improved = 0
    n_evaluated = 0

    for i, pair in enumerate(pairs):
        prompt = pair["prompt"]
        chosen = pair["chosen"]
        rejected = pair["rejected"]
        pair_type = pair.get("pair_type", "unknown")

        try:
            sft_chosen = sequence_log_prob(sft_model, tokenizer, prompt, chosen)
            sft_rejected = sequence_log_prob(sft_model, tokenizer, prompt, rejected)
            dpo_chosen = sequence_log_prob(dpo_model, tokenizer, prompt, chosen)
            dpo_rejected = sequence_log_prob(dpo_model, tokenizer, prompt, rejected)

            sft_delta = sft_chosen - sft_rejected
            dpo_delta = dpo_chosen - dpo_rejected
            improvement = dpo_delta - sft_delta
            improved = improvement > 0

            if improved:
                n_improved += 1
            n_evaluated += 1

            tag = "[BETTER]" if improved else "[WORSE]"
            print(
                f"Pair {i+1:2d} ({pair_type:12s}): "
                f"SFT delta={sft_delta:+.3f}  "
                f"DPO delta={dpo_delta:+.3f}  "
                f"improvement={improvement:+.3f}  {tag}"
            )

            pair_results.append({
                "pair": i + 1,
                "pair_type": pair_type,
                "sft_delta": round(sft_delta, 4),
                "dpo_delta": round(dpo_delta, 4),
                "improvement": round(improvement, 4),
                "improved": improved,
            })

        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                print(f"Pair {i+1}: OOM — skipped")
            else:
                raise

    verdict = "PASS" if n_improved >= PASS_THRESHOLD else "FAIL"
    print(f"\nRESULT: {n_improved}/{n_evaluated} pairs show DPO improvement  [{verdict}]")

    # D-12 generation smoke test
    print("\n[D-12 SMOKE] Testing generation ...")
    test_prompt = (
        "Which Canvas item is more urgent?\n"
        "Item A: [EXAM] Midterm 2 @CS2505 Tomorrow 200pts\n"
        "Item B: [ASGN] HW3 @CS2505 Due in 2 weeks 50pts\n"
        "Which is more urgent and why?"
    )
    inputs = tokenizer(test_prompt, return_tensors="pt").to(dpo_model.device)
    with torch.inference_mode():
        out = dpo_model.generate(**inputs, max_new_tokens=80, do_sample=False)
    n_prompt = inputs["input_ids"].shape[1]
    response = tokenizer.decode(out[0][n_prompt:], skip_special_tokens=True)
    print(f"[D-12 SMOKE] Response preview: {response[:120]}")
    assert len(response.strip()) > 10, "Model produced near-empty response — checkpoint may be corrupt"
    print("[D-12 SMOKE] PASS — checkpoint generates coherent output")

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "dpo_checkpoint": DPO_CHECKPOINT,
        "sft_checkpoint": SFT_CHECKPOINT,
        "n_pairs_evaluated": n_evaluated,
        "n_improved": n_improved,
        "pass_threshold": PASS_THRESHOLD,
        "verdict": verdict,
        "pairs": pair_results,
        "smoke_test_response_preview": response[:120],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nValidation report written: {REPORT_PATH}")

    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
