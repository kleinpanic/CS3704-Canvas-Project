"""
train_dpo_v3.py — DPO retrain with item-disjoint held-out split.

Differences from train_dpo.py (v2):
  - Reads data/dpo_train_v3.jsonl (998 records, item-disjoint from
    data/dpo_test_v3.jsonl per source/split_dpo_holdout.py).
  - Initializes from checkpoints/gguf/merged_bf16 (the surviving v2
    QLoRA-merged BF16 base; the standalone v2 SFT was lost).
  - Outputs to checkpoints/dpo-v3-checkpoint (does not overwrite v2).
  - Drops the second-pass oversample_hard_negatives call. The v3 input file
    is already pre-oversampled at data prep (hard×3); applying multiplier=3
    again at training time would yield the 9× effective rate documented in
    AUDIT-V4-RIGOR.md §1.6 as a v2 methodology bug. v3 fixes this — hard
    negatives appear at 3× as the paper §3.2 claims.
  - Otherwise identical hyperparams to v2: β=0.1, η=5e-7, 1 epoch,
    effective batch size 16 (per_device=2 × grad_accum=8), max_length=512,
    bf16, sigmoid loss.
  - Uses adamw_torch optimizer (matches v2 fallback under bnb-on-cuda-13.1).

Goal: produce a DPO checkpoint trainable to evaluate on items it has
never seen, so the validation report substantiates a true held-out claim
rather than a training-set fit measurement.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DATA_PATH = "./data/dpo_train_v3.jsonl"
SFT_CHECKPOINT_PATH = "./checkpoints/gguf/merged_bf16"
DPO_OUTPUT_DIR = "./checkpoints/dpo-v3-checkpoint"


def main():
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, Gemma4ForCausalLM
    from trl import DPOConfig, DPOTrainer

    print(f"[env] torch={torch.__version__} cuda={torch.cuda.is_available()}", flush=True)
    print(f"[data] {DATA_PATH}", flush=True)
    print(f"[base] {SFT_CHECKPOINT_PATH}", flush=True)
    print(f"[out ] {DPO_OUTPUT_DIR}", flush=True)

    Path(DPO_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(SFT_CHECKPOINT_PATH)
    tokenizer.padding_side = "left"
    print(f"[tok ] padding_side={tokenizer.padding_side}", flush=True)

    policy = Gemma4ForCausalLM.from_pretrained(
        SFT_CHECKPOINT_PATH, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    policy.config.use_cache = False
    ref = Gemma4ForCausalLM.from_pretrained(
        SFT_CHECKPOINT_PATH, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    print("[load] policy + ref loaded", flush=True)

    raw = load_dataset("json", data_files=DATA_PATH, split="train")
    print(f"[ds  ] n_examples={len(raw)} columns={raw.column_names}", flush=True)

    cfg = DPOConfig(
        output_dir=DPO_OUTPUT_DIR,
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=5e-7,
        beta=0.1,
        loss_type="sigmoid",
        bf16=True,
        max_length=512,
        gradient_checkpointing=True,
        optim="adamw_torch",
        precompute_ref_log_probs=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        sync_ref_model=False,
        seed=42,
    )

    trainer = DPOTrainer(
        model=policy,
        ref_model=ref,
        args=cfg,
        train_dataset=raw,
        processing_class=tokenizer,
    )

    print("[run ] training start", flush=True)
    train_result = trainer.train()

    trainer.save_model(DPO_OUTPUT_DIR)
    tokenizer.save_pretrained(DPO_OUTPUT_DIR)
    print(f"[done] checkpoint saved → {DPO_OUTPUT_DIR}", flush=True)

    metrics = train_result.metrics if hasattr(train_result, "metrics") else {}
    log_history = trainer.state.log_history if hasattr(trainer.state, "log_history") else []
    final_log = log_history[-1] if log_history else {}

    summary = {
        "checkpoint": DPO_OUTPUT_DIR,
        "data_path": DATA_PATH,
        "base_model": SFT_CHECKPOINT_PATH,
        "n_train_examples": len(raw),
        "trl_version": __import__("trl").__version__,
        "transformers_version": __import__("transformers").__version__,
        "hyperparams": {
            "beta": 0.1,
            "lr": 5e-7,
            "epochs": 1,
            "per_device_batch_size": 2,
            "grad_accum_steps": 8,
            "effective_batch_size": 16,
            "max_length": 512,
            "loss_type": "sigmoid",
            "optim": "adamw_torch",
            "seed": 42,
        },
        "train_metrics": metrics,
        "final_log_event": final_log,
    }
    import json
    Path(DPO_OUTPUT_DIR, "v3_run_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("[done] v3_run_summary.json written", flush=True)


if __name__ == "__main__":
    main()
