#!/usr/bin/env python3
"""
Canvas Item Reranker — Fine-tune Gemma 2B on Brev cloud GPU.

This script:
1. Generates augmented training data from Canvas item history
2. Spins up a Brev GPU instance (cheapest adequate for Gemma 2B)
3. Runs LoRA fine-tuning on Gemma 2B
4. Saves the adapter weights

Usage:
    python scripts/finetune_reranker.py --action setup     # create Brev instance
    python scripts/finetune_reranker.py --action train      # run training
    python scripts/finetune_reranker.py --action download  # pull weights back

Requirements:
    - brev CLI configured
    - brev python package installed
    - Gemma 2B model on HuggingFace (nvidia/Qwen3-8B-NVFP4)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path("/home/broklein/codeWS/Python/CS3704-Canvas-Project")
DATA_DIR = REPO_DIR / "data"
MODEL_NAME = "nvidia/Qwen3-8B-NVFP4"  # Gemma 2B — 8B needs ~16GB VRAM; 2B at 4-bit fits on L4/RTX4000
OUTPUT_DIR = DATA_DIR / "reranker_model"
TRAIN_DATA = DATA_DIR / "rerank_train.jsonl"
AUGMENTED_DATA = DATA_DIR / "rerank_train_augmented.jsonl"

# ── Training hyperparameters ──────────────────────────────────────────────────
LORA_RANK = 8
LORA_ALPHA = 16
LORA_DROPOUT = 0.05
BATCH_SIZE = 4
GRADIENT_ACCUMULATION = 4
LEARNING_RATE = 2e-4
NUM_EPOCHS = 3
MAX_SEQ_LEN = 256
FINETUNE_SCRIPT = "finetune_gemma.sh"


def generate_augmented_data() -> int:
    """Augment training data with more diverse query variations."""
    print("[INFO] Generating augmented training data...")

    import random
    from datetime import datetime, timezone, timedelta

    base_items = [
        {"key": "i001", "ptype": "assignment", "title": "CS 3704 Problem Set 3", "course_code": "CS3704", "due_iso": "2026-04-10T23:59:00Z", "points": 100.0, "status_flags": ["missing"]},
        {"key": "i002", "ptype": "quiz", "title": "NEUR 2464 Quiz 2", "course_code": "NEUR2464", "due_iso": "2026-04-11T22:00:00Z", "points": 25.0, "status_flags": ["late"]},
        {"key": "i003", "ptype": "assignment", "title": "HD 3114 Reading Response", "course_code": "HD3114", "due_iso": "2026-04-14T23:59:00Z", "points": 15.0, "status_flags": []},
        {"key": "i004", "ptype": "exam", "title": "CS 2505 Midterm 2", "course_code": "CS2505", "due_iso": "2026-04-15T23:59:00Z", "points": 200.0, "status_flags": []},
        {"key": "i005", "ptype": "discussion", "title": "NEUR 2464 Brain Discussion", "course_code": "NEUR2464", "due_iso": "2026-04-17T23:59:00Z", "points": 10.0, "status_flags": []},
        {"key": "i006", "ptype": "event", "title": "VT Spring Career Fair", "course_code": "VT", "due_iso": "2026-04-21T09:00:00Z", "points": 0.0, "status_flags": []},
        {"key": "i007", "ptype": "assignment", "title": "CS 3704 Lab 4", "course_code": "CS3704", "due_iso": "2026-04-08T23:59:00Z", "points": 50.0, "status_flags": ["submitted"]},
        {"key": "i008", "ptype": "assignment", "title": "HD 3114 Research Summary", "course_code": "HD3114", "due_iso": "2026-04-19T23:59:00Z", "points": 200.0, "status_flags": []},
        {"key": "i009", "ptype": "announcement", "title": "CS 3704 Final Guidelines", "course_code": "CS3704", "due_iso": "2026-04-16T12:00:00Z", "points": 0.0, "status_flags": []},
        {"key": "i010", "ptype": "quiz", "title": "NEUR 2464 fMRI Quiz", "course_code": "NEUR2464", "due_iso": "2026-04-18T22:00:00Z", "points": 30.0, "status_flags": []},
    ]

    TS = {"exam": 8, "quiz": 6, "assignment": 4, "discussion": 2, "event": 1, "announcement": 0}
    SS = {"missing": 10, "late": 5, "submitted": -50, "excused": -50}

    def urg(item):
        s = 0.0
        for f in item.get("status_flags", []):
            s += SS.get(f.lower(), 0)
        for t, v in TS.items():
            if t in item.get("ptype", "").lower():
                s += v
                break
        try:
            s += min(6, float(item.get("points") or 0) / 50)
        except:
            pass
        try:
            due = datetime.fromisoformat(item["due_iso"].replace("Z", "+00:00")).astimezone(timezone.utc)
            dh = (due - datetime.now(timezone.utc)).total_seconds() / 3600
            s += max(20, abs(dh) * 2) if dh < 0 else max(0, (168 - dh) / 24) * 2 if dh < 168 else 0
        except:
            pass
        return max(0, s)

    def show(item):
        badge = {"assignment": "ASGN", "quiz": "QUIZ", "exam": "EXAM", "discussion": "DISC", "event": "EVNT", "announcement": "NOTE"}.get(item["ptype"].lower(), "?")
        return f"[{badge}] {item['title'][:40]} @{item.get('course_code','')} due:{item['due_iso'][:10]} {item.get('points',0):.0f}pts"

    queries = ["due soon", "all items", "upcoming", "high priority", "check grades", "what to work on first", "sort by urgency", "order by deadline", "rank my tasks"]
    pairs = []
    scored = sorted(base_items, key=lambda x: -urg(x))
    seen = set()
    for i, a in enumerate(scored):
        for b in scored[i + 1:]:
            pk = (min(a["key"], b["key"]), max(a["key"], b["key"]))
            if pk in seen:
                continue
            seen.add(pk)
            ua, ub = urg(a), urg(b)
            q = random.choice(queries)
            pairs.append({
                "query": q,
                "item_a": show(a),
                "item_b": show(b),
                "preference": 1 if ua >= ub else 0,
                "urgency_a": round(ua, 2),
                "urgency_b": round(ub, 2),
                "reason": f"urgency {ua:.1f} vs {ub:.1f}"
            })

    with open(AUGMENTED_DATA, "w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")

    print(f"[OK] Generated {len(pairs)} training pairs")
    return len(pairs)


def write_training_script() -> str:
    """Write the bash training script that runs on Brev instance."""
    script = f"""#!/bin/bash
set -euo pipefail

echo "=== Canvas Item Reranker — Gemma 2B Fine-tune ==="
echo "Model: {MODEL_NAME}"
echo "Data: {TRAIN_DATA}"
echo "Output: {OUTPUT_DIR}"

# ── Environment ───────────────────────────────────────────────────────────────
export PYTHONUNBUFFERED=1
export HF_TOKEN="${HF_TOKEN:-}"

# ── Install deps ───────────────────────────────────────────────────────────────
pip install --quiet transformers datasets peft accelerate huggingface_hub bitsandbytes

# ── Clone/pull training data ───────────────────────────────────────────────────
mkdir -p {DATA_DIR}
if [ -f "{AUGMENTED_DATA}" ]; then
    echo "Using augmented data: {AUGMENTED_DATA}"
    TRAINFILE="{AUGMENTED_DATA}"
else
    echo "Using base data: {TRAIN_DATA}"
    TRAINFILE="{TRAIN_DATA}"
fi

# ── Download model ─────────────────────────────────────────────────────────────
echo "Downloading {MODEL_NAME}..."
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(repo_id='{MODEL_NAME}', local_dir='/root/gemma-2b')
"
MODEL_DIR="/root/gemma-2b"

# ── Format data for training ────────────────────────────────────────────────────
echo "Formatting training data..."
python3 << 'PYEOF'
import json

with open('{AUGMENTED_DATA}') as f:
    pairs = [json.loads(l) for l in f]

# Format as instruction-style examples
lines = []
for p in pairs:
    q = p['query']
    a = p['item_a']
    b = p['item_b']
    pref = p['preference']
    label = "A" if pref == 1 else "B"

    text = (
        f"Query: {q}\n"
        f"Option A: {a}\n"
        f"Option B: {b}\n"
        f"Which should be ranked higher? Answer: {label} because {p['reason']}"
    )
    lines.append({"text": text, "label": label, "urgency_a": p["urgency_a"], "urgency_b": p["urgency_b"]})

with open('/tmp/formatted_train.jsonl', 'w') as f:
    for l in lines:
        f.write(json.dumps(l) + '\n')
print(f'Formatted {len(lines)} examples')
PYEOF

# ── Fine-tune with LoRA ────────────────────────────────────────────────────────
echo "Starting LoRA fine-tune..."
python3 << 'PYEOF'
import os, json, torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from peft import get_peft_model, LoraConfig, TaskType
from datasets import Dataset

# Load model in 4-bit
model_id = "/root/gemma-2b"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto",
    torch_dtype=torch.float16,
    load_in_4bit=True,
)

# LoRA config
lora_cfg = LoraConfig(
    r={LORA_RANK},
    lora_alpha={LORA_ALPHA},
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    lora_dropout={LORA_DROPOUT},
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(model, lora_cfg)
model.print_trainable_parameters()

# Load data
with open('/tmp/formatted_train.jsonl') as f:
    items = [json.loads(l) for l in f]

def tokenize(ex):
    txt = f"Query: {ex['text']}\nAnswer: "
    enc = tokenizer(txt, truncation=True, max_length={MAX_SEQ_LEN}, padding="max_length")
    enc["labels"] = enc["input_ids"][:]
    return enc

ds = Dataset.from_list(items).map(tokenize, batched=False, remove_columns=["text", "label", "urgency_a", "urgency_b"])

args = TrainingArguments(
    output_dir="/tmp/reranker_model",
    per_device_train_batch_size={BATCH_SIZE},
    gradient_accumulation_steps={GRADIENT_ACCUMULATION},
    learning_rate={LEARNING_RATE},
    num_train_epochs={NUM_EPOCHS},
    fp16=True,
    logging_steps=5,
    save_strategy="epoch",
    report_to="none",
)

trainer = Trainer(model=model, args=args, train_dataset=ds, tokenizer=tokenizer)
trainer.train()

# Save adapter
model.save_pretrained("{OUTPUT_DIR}")
tokenizer.save_pretrained("{OUTPUT_DIR}")
print("Training complete! Adapter saved to {OUTPUT_DIR}")
PYEOF

echo "Done. Model adapter at {OUTPUT_DIR}"
ls -la {OUTPUT_DIR}
"""
    return script


def run_brev_setup() -> str:
    """Create a Brev GPU instance for fine-tuning."""
    print("[INFO] Setting up Brev GPU instance for Gemma 4B fine-tuning...")

    result = subprocess.run(
        ["brev", "instance", "create",
         "--name", "canvas-reranker-gemma",
         "--gpu", "1",
         "--machine", "L4",     # 24GB VRAM — plenty for Gemma 2B at 4-bit, cheaper than L40S
         "--region", "us-east-1",
         "--framework", "python",
         "--jupyter",
         "--yes"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[WARN] Brev instance create: {result.stderr}")
        return ""
    inst_id = result.stdout.strip().split("\n")[-1].split()[0]
    print(f"[OK] Instance: {inst_id}")
    return inst_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune Gemma 2B reranker on Brev")
    parser.add_argument("--action", choices=["setup", "train", "download", "generate-data"], default="generate-data")
    parser.add_argument("--instance-id", help="Brev instance ID (for train/download)")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Local output path for model")
    args = parser.parse_args()

    if args.action == "generate-data":
        n = generate_augmented_data()
        print(f"[OK] {n} training pairs generated at {AUGMENTED_DATA}")
        return

    if args.action == "setup":
        inst_id = run_brev_setup()
        if not inst_id:
            print("[ERROR] Failed to create Brev instance")
            sys.exit(1)
        print(f"[OK] Brev instance {inst_id} created. Run --action train --instance-id {inst_id}")
        return

    if args.action == "train":
        if not args.instance_id:
            print("[ERROR] --instance-id required for train action")
            sys.exit(1)

        script = write_training_script()
        script_path = REPO_DIR / "scripts" / FINETUNE_SCRIPT
        script_path.write_text(script)
        script_path.chmod(0o755)

        print(f"[INFO] Sending training script to Brev instance {args.instance_id}...")
        # brev exec <instance> -- bash -c "$(cat script)"
        result = subprocess.run(
            ["brev", "exec", args.instance_id, "--file", str(script_path)],
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"[ERROR] {result.stderr}")
        return

    if args.action == "download":
        if not args.instance_id:
            print("[ERROR] --instance-id required for download action")
            sys.exit(1)
        local = Path(args.output)
        local.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Downloading model from instance {args.instance_id} to {local}")
        result = subprocess.run(
            ["brev", "copy", args.instance_id + ":" + str(OUTPUT_DIR), str(local)],
            capture_output=True, text=True
        )
        print(result.stdout or "[OK] copy initiated")


if __name__ == "__main__":
    main()