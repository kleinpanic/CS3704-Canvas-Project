"""
bench_v4_methods.py — apples-to-apples comparison of all 6 v4 method
variants on the v3 held-out test partition (n=148 item-disjoint
standard pairs).

For each method's checkpoint:
  - load via transformers (PEFT-wrapped if adapter)
  - greedy-decode chat-template prompts
  - extract first "Item A"/"Item B" → score vs gold from chosen text
  - report pairwise accuracy + Wilson 95% CI + cross-variant agreement

Output: checkpoints/benchmark/v4_methods_benchmark.json + a printed
markdown comparison table suitable for paper §6.7 + HF model cards.
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

TEST_PATH = Path("data/dpo_test_v3.jsonl")
BASE_FOR_ADAPTERS = "checkpoints/gemma4-text-base"
OUT_PATH = Path("checkpoints/benchmark/v4_methods_benchmark.json")

VARIANTS = [
    {"method": "ref",      "ckpt": "checkpoints/gguf/merged_bf16",  "is_adapter": False, "label": "merged_bf16 (v2 reference)"},
    {"method": "sft",      "ckpt": "checkpoints/v4-sft",             "is_adapter": False, "label": "SFT v4"},
    {"method": "lora",     "ckpt": "checkpoints/v4-lora",            "is_adapter": True,  "label": "LoRA v4"},
    {"method": "qlora",    "ckpt": "checkpoints/v4-qlora",           "is_adapter": True,  "label": "QLoRA v4"},
    {"method": "dpo",      "ckpt": "checkpoints/v4-dpo",             "is_adapter": False, "label": "DPO v4 (sigmoid, Rafailov 2023)"},
    {"method": "ipo",      "ckpt": "checkpoints/v4-ipo",             "is_adapter": False, "label": "IPO v4 (Azar 2023)"},
    {"method": "apo_zero", "ckpt": "checkpoints/v4-apo-zero",        "is_adapter": False, "label": "APO-zero v4 (Pan 2024)"},
    {"method": "sppo",     "ckpt": "checkpoints/v4-sppo",            "is_adapter": False, "label": "SPPO v4 (Wu 2024)"},
    {"method": "nca",      "ckpt": "checkpoints/v4-nca",             "is_adapter": False, "label": "NCA v4 (Chen 2024)"},
    {"method": "kto",      "ckpt": "checkpoints/v4-kto",             "is_adapter": False, "label": "KTO v4 (Ethayarajh 2024)"},
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


def load_model(variant: dict):
    import torch
    from transformers import AutoTokenizer, Gemma4ForCausalLM
    ckpt = variant["ckpt"]
    if variant["is_adapter"]:
        from peft import PeftModel
        base = Gemma4ForCausalLM.from_pretrained(
            BASE_FOR_ADAPTERS, torch_dtype=torch.bfloat16,
            attn_implementation="sdpa", device_map="auto",
        )
        model = PeftModel.from_pretrained(base, ckpt)
    else:
        model = Gemma4ForCausalLM.from_pretrained(
            ckpt, torch_dtype=torch.bfloat16,
            attn_implementation="sdpa", device_map="auto",
        )
    model.train(False)
    tok = AutoTokenizer.from_pretrained(ckpt if not variant["is_adapter"] else BASE_FOR_ADAPTERS)
    return model, tok


def benchmark(variant: dict, pairs: list[dict]) -> dict:
    import torch
    if not Path(variant["ckpt"]).exists():
        return {"method": variant["method"], "error": f"missing checkpoint {variant['ckpt']}"}

    print(f"\n[{variant['method']}] loading {variant['ckpt']} ...")
    model, tok = load_model(variant)
    print(f"[{variant['method']}] loaded; n_params(trainable)={sum(p.numel() for p in model.parameters() if p.requires_grad):,}")

    n_correct = 0
    n_abstain = 0
    preds = []
    for i, pair in enumerate(pairs):
        prompt = pair["prompt"]
        gold = chosen_picks(pair["chosen"])
        chat = tok.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False, add_generation_prompt=True,
        )
        enc = tok(chat, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(
                **enc, max_new_tokens=32, do_sample=False,
                pad_token_id=tok.pad_token_id or tok.eos_token_id,
            )
        n_prompt = enc["input_ids"].shape[1]
        text = tok.decode(out[0][n_prompt:], skip_special_tokens=True)
        pred = chosen_picks(text)
        preds.append({"pair": i + 1, "gold": gold, "pred": pred})
        if pred is None:
            n_abstain += 1
        elif pred == gold:
            n_correct += 1
        if (i + 1) % 25 == 0:
            print(f"  [{i+1:3d}/{len(pairs)}] correct={n_correct}")

    n_scored = len(pairs) - n_abstain
    acc = n_correct / n_scored if n_scored else 0.0
    lo, hi = wilson_ci(n_correct, n_scored)

    # Free GPU before next variant
    del model
    import gc; gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "method": variant["method"],
        "label": variant["label"],
        "ckpt": variant["ckpt"],
        "n_pairs": len(pairs),
        "n_correct": n_correct,
        "n_scored": n_scored,
        "n_abstain": n_abstain,
        "pairwise_accuracy": round(acc, 4),
        "wilson_95ci": [round(lo, 4), round(hi, 4)],
        "predictions": preds,
    }


def main():
    pairs = [json.loads(l) for l in TEST_PATH.read_text().splitlines() if l.strip()]
    print(f"[load] {len(pairs)} held-out pairs from {TEST_PATH}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    variants_to_run = [v for v in VARIANTS if not only or v["method"] == only]

    results = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "test_data": str(TEST_PATH),
        "n_pairs": len(pairs),
        "test_partition": "v3 item-disjoint, 148 standard pairs (zero hard-neg)",
        "variants": {},
    }
    for variant in variants_to_run:
        results["variants"][variant["method"]] = benchmark(variant, pairs)
        OUT_PATH.write_text(json.dumps(results, indent=2))
        print(f"[saved] {OUT_PATH}")

    # Cross-variant agreement matrix (which methods make the same prediction?)
    methods_with_results = [m for m in results["variants"] if "predictions" in results["variants"][m]]
    if len(methods_with_results) > 1:
        print(f"\n=== Cross-variant prediction agreement ===")
        for i, m1 in enumerate(methods_with_results):
            for m2 in methods_with_results[i+1:]:
                p1 = results["variants"][m1]["predictions"]
                p2 = results["variants"][m2]["predictions"]
                agree = sum(1 for a, b in zip(p1, p2) if a["pred"] == b["pred"])
                print(f"  {m1:8s} vs {m2:8s}: {agree}/{len(p1)} agreement")

    print(f"\n{'='*78}")
    print(f"  V4 METHOD COMPARISON  (n={len(pairs)} held-out, item-disjoint)")
    print(f"{'='*78}")
    print(f"  {'Method':>10s}  {'n_correct':>9s}  {'Acc':>7s}  {'Wilson 95% CI':>20s}  {'Abstain':>7s}")
    for m in methods_with_results:
        r = results["variants"][m]
        ci = r["wilson_95ci"]
        ci_str = f"[{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]"
        print(f"  {m:>10s}  {r['n_correct']:>4d}/{r['n_scored']:<4d}  {r['pairwise_accuracy']*100:>5.1f}%  {ci_str:>20s}  {r['n_abstain']:>7d}")


if __name__ == "__main__":
    main()
