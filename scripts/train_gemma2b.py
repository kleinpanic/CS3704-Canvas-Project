#!/usr/bin/env python3
"""
Gemma 2B Reranker — QLoRA Fine-Tune Script
===========================================
Trains google/gemma-2b-it as a Canvas priority reranker using QLoRA + SFTTrainer.

Hardware: NVIDIA DGX Spark GB10 (128GB UMA) or any GPU with >= 8GB total memory.
          BF16 loading: ~4.5GB VRAM. Fits alongside Nemotron on GB10 with headroom.

Usage:
    # Option A: via Spark trainer container (preferred on Spark)
    docker compose run --rm trainer \
        python3 /workspace/scripts/train_gemma2b.py \
            --data /workspace/data/rerank_sft.jsonl \
            --output /workspace/outputs/gemma2b-reranker \
            --epochs 3

    # Option B: via Python venv/script directly (broklein or local)
    python3 scripts/train_gemma2b.py \
        --data ~/codeWS/Gemma2B-Reranker/data/rerank_sft.jsonl \
        --output ~/codeWS/Gemma2B-Reranker/outputs/gemma2b-reranker \
        --epochs 3

    # Option C: full Docker on any GPU machine
    docker run --gpus all --ipc=host --shm-size=8g \
        -v $(pwd):/workspace \
        gemma2b-trainer \
        python3 /workspace/scripts/train_gemma2b.py \
            --data /workspace/data/rerank_sft.jsonl \
            --output /workspace/outputs/gemma2b-reranker \
            --epochs 3

Outputs:
    outputs/gemma2b-reranker/
        adapter_config.json   # LoRA adapter config
        adapter_model.safetensors  # LoRA weights (4-bit)
        trainer_state.json     # training metrics
        convergence_loss.json  # final loss snapshot
"""

import argparse
import gc
import json
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import torch
from transformers import AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer

# Optional: bitsandbytes for strict 4-bit loading (set by Dockerfile mostly)
try:
    import bitsandbytes as bnb
    BNB_AVAILABLE = True
except ImportError:
    BNB_AVAILABLE = False

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Model & Training Config ────────────────────────────────────────────────────
BASE_MODEL = "google/gemma-2b-it"

LORA_CONFIG = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=64,                          # LoRA rank — 64 is good for 2B models
    lora_alpha=128,                # scaling = lora_alpha / r = 2.0
    lora_dropout=0.05,
    target_modules=[                # Gemma 2B attention modules
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    bias="none",
    inference_mode=False,
)

# QLoRA bitsandbytes config — applied at model loading
def get_bnb_config():
    if not BNB_AVAILABLE:
        return None
    return {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",         # Normal Float 4 — optimal for pretrained
        "bnb_4bit_compute_dtype": torch.bfloat16,  # BF16 for training compute
        "bnb_4bit_use_double_quant": True,      # saves ~0.4 bits/param via double quant
    }

# SFTTrainer hyperparameters
SFT_ARGS = {
    "per_device_train_batch_size": 1,     # Gemma 2B is small; batch 1 is fine
    "gradient_accumulation_steps": 16,   # effective batch = 16 × 1 = 16
    "warmup_steps": 3,
    "learning_rate": 2e-4,
    "weight_decay": 0.01,
    "fp16": False,
    "bf16": True,                          # GB10 supports BF16 natively
    "logging_steps": 10,
    "optim": "paged_adamw_32bit",           # paged — NVIDIA extension, falls back gracefully
    "lr_scheduler_type": "cosine",
    "seed": 42,
    "report_to": "none",                   # no wandb needed
    "max_grad_norm": 0.3,
}


# ── Data Formatting ───────────────────────────────────────────────────────────
def load_sft_data(path: str) -> list[dict]:
    """Load SFTTrainer JSONL. Each line: {"text": "...", ...}"""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def format_sample(example: dict) -> dict:
    """Map our JSONL fields to SFTTrainer's expected format."""
    return {"text": example["text"]}


# ── Training ───────────────────────────────────────────────────────────────────
def train(
    data_path: str,
    output_dir: str,
    epochs: int = 3,
    max_seq_len: int = 256,
    resume_from: str | None = None,
):
    print("=" * 60)
    print("Gemma 2B Reranker — QLoRA Fine-Tune")
    print(f"  Base model: {BASE_MODEL}")
    print(f"  Data:       {data_path}")
    print(f"  Output:     {output_dir}")
    print(f"  Epochs:     {epochs}")
    print(f"  Max seq:    {max_seq_len}")
    print(f"  BF16:       {SFT_ARGS['bf16']}")
    print(f"  QLoRA r:    {LORA_CONFIG.r}")
    print(f"  BNB avail:  {BNB_AVAILABLE}")
    print(f"  GPU:        {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    print(f"  GPU mem:    {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB" if torch.cuda.is_available() else "  GPU mem:    N/A")
    print("=" * 60)

    t0 = time.time()

    # ── Tokenizer ───────────────────────────────────────────────────────────────
    print("\n[1/5] Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL,
        trust_remote_code=True,
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    tokenizer.model_max_length = max_seq_len

    # ── Data ───────────────────────────────────────────────────────────────────
    print("[2/5] Loading dataset...")
    raw_data = load_sft_data(data_path)
    train_data = [format_sample(ex) for ex in raw_data]
    from datasets import Dataset
    train_data = Dataset.from_list(train_data)
    print(f"  Loaded {len(train_data)} training examples")

    # ── Model with QLoRA ────────────────────────────────────────────────────────
    print("[3/5] Loading model with QLoRA config...")
    from transformers import AutoModelForCausalLM
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )

    # Print trainable param count
    model = get_peft_model(model, LORA_CONFIG)
    model.print_trainable_parameters()

    # ── Training Arguments ──────────────────────────────────────────────────────
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_path),
        num_train_epochs=epochs,
        max_steps=-1,
        save_strategy="no",             # We save manually after training
        save_only_model=True,
        dataloader_num_workers=2,
        remove_unused_columns=False,
        **SFT_ARGS,
    )

    # ── SFTTrainer ─────────────────────────────────────────────────────────────
    print("[4/5] Starting fine-tune...")
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_data,
        processing_class=tokenizer,
        formatting_func=lambda x: x["text"],
    )

    # Suppress SDPA flash attention warning
    trainer.model.config.use_cache = False

    # Snapshot loss before training (baseline)
    baseline_loss = None  # init: set to None, computed below if resuming from scratch
    # Snapshot loss before training (baseline) — must be BEFORE SFTTrainer processes data
    baseline_loss = None
    if resume_from is None:
        print("  Running baseline eval (first 50 samples)...")
        sample_texts = [train_data[i]["text"] for i in range(min(50, len(train_data)))]
        encs = tokenizer(sample_texts, return_tensors="pt", truncation=True,
                         max_length=max_seq_len, padding=True)
        with torch.no_grad():
            outs = trainer.model(input_ids=encs.input_ids.to(trainer.model.device),
                                 attention_mask=encs.attention_mask.to(trainer.model.device))
            # rough per-token loss
            logits = outs.logits
            labels = encs.input_ids.to(logits.device)
            loss_fct = torch.nn.CrossEntropyLoss(reduction="mean")
            shift_logits = logits[..., :-1, :].contiguous()
            shift_labels = labels[..., 1:].contiguous()
            baseline_loss = loss_fct(shift_logits.view(-1, shift_logits.size(-1)),
                                      shift_labels.view(-1)).item()
        print(f"  Baseline loss (first 50 samples): {baseline_loss:.4f}")
        (output_path / "baseline_loss.json").write_text(json.dumps({
            "baseline_loss": baseline_loss,
            "num_samples": 50,
            "timestamp": datetime.utcnow().isoformat(),
        }))

    # Train
    if resume_from is not None:
        trainer.train(resume_from_checkpoint=resume_from)
    else:
        trainer.train()

    # ── Save ────────────────────────────────────────────────────────────────────
    print("[5/5] Saving adapter...")
    trainer.save_model(str(output_path))
    trainer.save_state()

    # Final loss
    final_loss = trainer.state.log_history[-1].get("loss", None)
    elapsed = time.time() - t0

    # Save convergence snapshot
    (output_path / "convergence_loss.json").write_text(json.dumps({
        "final_loss": final_loss,
        "baseline_loss": baseline_loss if resume_from is None else None,
        "delta": (baseline_loss - final_loss) if (resume_from is None and final_loss) else None,
        "num_trainable_params": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "total_params": sum(p.numel() for p in model.parameters()),
        "lora_rank": LORA_CONFIG.r,
        "lora_alpha": LORA_CONFIG.lora_alpha,
        "epochs": epochs,
        "effective_batch_size": SFT_ARGS["per_device_train_batch_size"] * SFT_ARGS["gradient_accumulation_steps"],
        "elapsed_seconds": round(elapsed),
        "timestamp": datetime.utcnow().isoformat(),
    }, indent=2))

    print(f"\n✓ Training complete in {elapsed / 60:.1f} min")
    print(f"  Final loss: {final_loss:.4f}" if final_loss else "  Final loss: N/A")
    print(f"  Saved to: {output_path}")
    print(f"\nNext: python3 scripts/benchmark.py --adapter {output_path} ...")
    return output_path


# ── CLI ────────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="QLoRA fine-tune Gemma 2B as Canvas reranker")
    p.add_argument("--data", required=True, help="Path to rerank_sft.jsonl")
    p.add_argument("--output", required=True, help="Output dir for LoRA adapter")
    p.add_argument("--epochs", type=int, default=3, help="Training epochs (default: 3)")
    p.add_argument("--max-seq-len", type=int, default=256, help="Max sequence length (default: 256)")
    p.add_argument("--resume-from", default=None, help="Path to existing adapter to resume")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(
        data_path=args.data,
        output_dir=args.output,
        epochs=args.epochs,
        max_seq_len=args.max_seq_len,
        resume_from=args.resume_from,
    )
