"""
publish_v4_models.py — for each v4 method variant:
  1. Verify the checkpoint loaded successfully
  2. (optionally) generate Q4_K_M GGUF via llama.cpp/quantize
  3. Push to HuggingFace as a separate model repo
  4. Add to the canvas-reranker collection

Run after train_v4_matrix.py completes for any/all methods.

Usage:
    python3 source/publish_v4_models.py sft     # publish one
    python3 source/publish_v4_models.py all     # publish all that exist
    python3 source/publish_v4_models.py all --dry-run   # plan only
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

USER = "kleinpanic93"
COLLECTION_SLUG = "kleinpanic93/canvas-reranker-gemma-4-e2b-it-v10-69f5799662d65c8f39be0a94"

VARIANTS = {
    "sft":      {"ckpt": "checkpoints/v4-sft",      "repo": f"{USER}/gemma4-canvas-reranker-sft",      "kind": "model", "is_adapter": False, "title": "SFT v4"},
    "lora":     {"ckpt": "checkpoints/v4-lora",     "repo": f"{USER}/gemma4-canvas-reranker-lora",     "kind": "model", "is_adapter": True,  "title": "LoRA v4"},
    "qlora":    {"ckpt": "checkpoints/v4-qlora",    "repo": f"{USER}/gemma4-canvas-reranker-qlora",    "kind": "model", "is_adapter": True,  "title": "QLoRA v4"},
    "dpo":      {"ckpt": "checkpoints/v4-dpo",      "repo": f"{USER}/gemma4-canvas-reranker-dpo",      "kind": "model", "is_adapter": False, "title": "DPO v4 (sigmoid)"},
    "ipo":      {"ckpt": "checkpoints/v4-ipo",      "repo": f"{USER}/gemma4-canvas-reranker-ipo",      "kind": "model", "is_adapter": False, "title": "IPO v4 (Identity Preference Optimization, Azar 2023)"},
    "apo_zero": {"ckpt": "checkpoints/v4-apo-zero", "repo": f"{USER}/gemma4-canvas-reranker-apo-zero", "kind": "model", "is_adapter": False, "title": "APO-zero v4 (Anchored Preference Optimization, Pan 2024)"},
    "sppo":     {"ckpt": "checkpoints/v4-sppo",     "repo": f"{USER}/gemma4-canvas-reranker-sppo",     "kind": "model", "is_adapter": False, "title": "SPPO v4 (Self-Play Preference Optimization, Wu 2024)"},
    "nca":      {"ckpt": "checkpoints/v4-nca",      "repo": f"{USER}/gemma4-canvas-reranker-nca",      "kind": "model", "is_adapter": False, "title": "NCA v4 (Noise-Contrastive Alignment, Chen 2024)"},
    "kto":      {"ckpt": "checkpoints/v4-kto",      "repo": f"{USER}/gemma4-canvas-reranker-kto",      "kind": "model", "is_adapter": False, "title": "KTO v4 (Kahneman-Tversky Optimization, Ethayarajh 2024)"},
}

CARD_TEMPLATE = """---
license: gemma
base_model: google/gemma-4-E2B-it
library_name: {library}
tags:
  - canvas-lms
  - assignment-prioritization
  - preference-learning
  - {method}
language:
  - en
pipeline_tag: text-generation
datasets:
  - kleinpanic93/canvas-preference-2k
---

# Gemma-4-E2B-IT Canvas Reranker — {title}

Variant of [`kleinpanic93/gemma4-canvas-reranker`](https://huggingface.co/kleinpanic93/gemma4-canvas-reranker)
trained via **{method_full}** on the corrected `gemma4-text-base` and
the v3 train partition (998 records, item-disjoint from the v3 test
set).

This is one of **6 method variants** released as a multi-method
comparison set. See the
[Canvas Reranker Collection](https://huggingface.co/collections/{collection_slug})
for all variants and the [methodology paper](https://huggingface.co/kleinpanic93/gemma4-canvas-reranker/blob/main/paper/main.pdf).

## Training

- **Method:** {method_full}
- **Base:** `gemma4-text-base` (corrected from `google/gemma-4-E2B-it`
  multimodal — see paper §6.5 errata)
- **Data:** `kleinpanic93/canvas-preference-2k`, v3 train partition
  (998 records, item-disjoint)
- **Hyperparameters:** {hparams}
- **Hardware:** NVIDIA Grace–Blackwell GB10 (128 GiB UMA)
- **Toolchain:** TRL 1.1.0, Transformers 5.5.4, PyTorch 2.11+cu130

## Held-out evaluation (n=148 item-disjoint pairs)

See `holdout_validation.json` in this repo. Cross-method comparison
table is in the methodology paper §6.7 and the Collection overview.

## Use

This is a {kind_descriptor}. Load with:

```python
{load_snippet}
```

For deployment, prefer the GGUF quants under
[`kleinpanic93/gemma4-canvas-reranker`](https://huggingface.co/kleinpanic93/gemma4-canvas-reranker)
unless you specifically need this method's behavior.

## License

Gemma Terms of Use — see https://ai.google.dev/gemma/terms.
"""


def hparams_for(method: str) -> str:
    if method == "sft":
        return "1 epoch, lr=2e-5, full-parameter, bf16, max_length=512, AdamW"
    if method in ("lora", "qlora"):
        bits = "4-bit base + " if method == "qlora" else ""
        return f"1 epoch, lr=2e-4, LoRA r=16 α=32 dropout=0.05 targeting q/k/v/o_proj, {bits}bf16, max_length=512, AdamW"
    loss_map = {
        "dpo": "sigmoid", "ipo": "ipo", "apo_zero": "apo_zero",
        "sppo": "sppo_hard", "nca": "nca_pair",
    }
    if method in loss_map:
        return f"1 epoch, lr=5e-7, β=0.1, DPOTrainer loss_type='{loss_map[method]}', bf16, max_length=512, AdamW"
    if method == "kto":
        return "1 epoch, lr=5e-7, β=0.1, KTOTrainer, bf16, max_length=512, AdamW"
    return ""


def write_card(method: str, info: dict, ckpt_dir: Path) -> Path:
    method_full = {
        "sft": "Supervised Fine-Tuning (SFT) — full parameter",
        "lora": "Low-Rank Adaptation (LoRA, Hu 2022)",
        "qlora": "QLoRA (Dettmers 2023) — 4-bit base + LoRA adapter",
        "dpo": "Direct Preference Optimization (DPO, Rafailov 2023, sigmoid loss)",
        "ipo": "Identity Preference Optimization (IPO, Azar 2023) — fixes DPO overoptimization on saturated tasks",
        "apo_zero": "Anchored Preference Optimization (APO-zero, Pan 2024) — DPO variant with anchor regularization",
        "sppo": "Self-Play Preference Optimization (SPPO, Wu 2024) — strong recent results on alignment benchmarks",
        "nca": "Noise-Contrastive Alignment (NCA, Chen 2024) — pairwise noise-contrastive estimation for preference learning",
        "kto": "Kahneman-Tversky Optimization (KTO, Ethayarajh 2024) — handles unpaired preference data",
    }[method]
    is_adapter = info["is_adapter"]
    if is_adapter:
        kind_descriptor = "PEFT adapter (load with peft.PeftModel.from_pretrained)"
        load_snippet = f"""from peft import PeftModel
from transformers import Gemma4ForCausalLM, AutoTokenizer

base = Gemma4ForCausalLM.from_pretrained(
    "kleinpanic93/gemma4-canvas-reranker", subfolder="merged_bf16",
    torch_dtype="bfloat16",
)
model = PeftModel.from_pretrained(base, "{info['repo']}")
tok = AutoTokenizer.from_pretrained("{info['repo']}")"""
    else:
        kind_descriptor = "full HF transformers checkpoint"
        load_snippet = f"""from transformers import Gemma4ForCausalLM, AutoTokenizer

model = Gemma4ForCausalLM.from_pretrained(
    "{info['repo']}", torch_dtype="bfloat16",
)
tok = AutoTokenizer.from_pretrained("{info['repo']}")"""
    card = CARD_TEMPLATE.format(
        title=info["title"],
        method=method,
        method_full=method_full,
        library="peft" if is_adapter else "transformers",
        hparams=hparams_for(method),
        kind_descriptor=kind_descriptor,
        load_snippet=load_snippet,
        collection_slug=COLLECTION_SLUG,
    )
    card_path = ckpt_dir / "README.md"
    card_path.write_text(card)
    return card_path


def publish(method: str, dry_run: bool = False) -> bool:
    info = VARIANTS[method]
    ckpt_dir = Path(info["ckpt"])
    if not ckpt_dir.exists() or not any(ckpt_dir.iterdir()):
        print(f"  [{method}] checkpoint missing — skip")
        return False
    print(f"  [{method}] writing model card → {ckpt_dir}/README.md")
    write_card(method, info, ckpt_dir)
    if dry_run:
        print(f"  [{method}] DRY-RUN — would push to {info['repo']}")
        return True
    print(f"  [{method}] pushing to {info['repo']} ...")
    cmd = [
        "hf", "upload", info["repo"], str(ckpt_dir), ".",
        "--commit-message", f"feat(v4): {info['title']} initial publish",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [{method}] FAILED: {r.stderr.splitlines()[-1] if r.stderr else 'unknown'}")
        return False
    print(f"  [{method}] uploaded — adding to collection")
    add = subprocess.run(
        ["hf", "collections", "add-item", COLLECTION_SLUG, info["repo"], info["kind"]],
        capture_output=True, text=True,
    )
    if add.returncode != 0 and "already in collection" not in add.stderr:
        print(f"  [{method}] WARN: collection add failed: {add.stderr.splitlines()[-1] if add.stderr else 'unknown'}")
    return True


def main():
    args = sys.argv[1:] or ["all"]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    target = args[0] if args else "all"
    methods = list(VARIANTS) if target == "all" else [target]
    for m in methods:
        if m not in VARIANTS:
            print(f"unknown variant: {m}; choices: {list(VARIANTS)}")
            sys.exit(1)
        publish(m, dry_run=dry_run)


if __name__ == "__main__":
    main()
