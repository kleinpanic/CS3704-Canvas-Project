"""
train_v4_matrix.py — train all 6 method variants from gemma4-text-base
on the v3 train partition (998 records, item-disjoint from v3 test).

Methods (TRL 1.1.0 — what the env supports today):
  - sft        : SFTTrainer, full-parameter, 1 epoch, lr 2e-5
  - lora       : SFTTrainer + LoraConfig (r=16, q/k/v/o), 1 epoch, lr 2e-4
  - qlora      : SFTTrainer + 4-bit base + LoraConfig, 1 epoch, lr 2e-4
  - dpo        : DPOTrainer, loss_type="sigmoid" (canonical DPO), β=0.1
  - ipo        : DPOTrainer, loss_type="ipo" (Identity PO, Azar 2023)
  - kto        : KTOTrainer (Kahneman-Tversky, Ethayarajh 2024)

Each method writes to checkpoints/v4-{method}/.

Usage:
    python3 source/train_v4_matrix.py sft
    python3 source/train_v4_matrix.py all   # sequentially train all 6
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BASE = "checkpoints/gemma4-text-base"
DPO_DATA = "data/dpo_train_v3.jsonl"           # 998 records, prompt/chosen/rejected
SFT_DATA = "data/sft_train_v3.jsonl"           # derived: prompt/completion only
KTO_DATA = "data/kto_train_v3.jsonl"           # derived: KTO format
OUT_ROOT = Path("checkpoints")
SEED = 42


def derive_sft_data():
    """Reduce dpo_train_v3 → (prompt, completion=chosen) for SFT/LoRA/QLoRA."""
    if Path(SFT_DATA).exists():
        print(f"  [skip] {SFT_DATA} already exists")
        return
    out = []
    for line in open(DPO_DATA):
        r = json.loads(line)
        out.append({"prompt": r["prompt"], "completion": r["chosen"]})
    Path(SFT_DATA).write_text("\n".join(json.dumps(r) for r in out) + "\n")
    print(f"  [wrote] {SFT_DATA} ({len(out)} records)")


def derive_kto_data():
    """KTO format: {prompt, completion, label} where label=True for chosen,
    False for rejected. Each DPO record produces TWO KTO records."""
    if Path(KTO_DATA).exists():
        print(f"  [skip] {KTO_DATA} already exists")
        return
    out = []
    for line in open(DPO_DATA):
        r = json.loads(line)
        out.append({"prompt": r["prompt"], "completion": r["chosen"], "label": True})
        out.append({"prompt": r["prompt"], "completion": r["rejected"], "label": False})
    Path(KTO_DATA).write_text("\n".join(json.dumps(r) for r in out) + "\n")
    print(f"  [wrote] {KTO_DATA} ({len(out)} records)")


def train_sft(out_dir: Path):
    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, Gemma4ForCausalLM
    from trl import SFTConfig, SFTTrainer

    print(f"[sft] loading base from {BASE}")
    tok = AutoTokenizer.from_pretrained(BASE)
    tok.padding_side = "right"
    model = Gemma4ForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    model.config.use_cache = False
    raw = load_dataset("json", data_files=SFT_DATA, split="train")
    cfg = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=2e-5,
        bf16=True,
        max_length=512,
        gradient_checkpointing=True,
        optim="adamw_torch",
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        seed=SEED,
    )
    SFTTrainer(model=model, args=cfg, train_dataset=raw, processing_class=tok).train()
    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))


def train_lora(out_dir: Path, four_bit: bool):
    import torch
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoTokenizer, BitsAndBytesConfig, Gemma4ForCausalLM
    from trl import SFTConfig, SFTTrainer

    print(f"[{'qlora' if four_bit else 'lora'}] loading base from {BASE} (4-bit={four_bit})")
    tok = AutoTokenizer.from_pretrained(BASE)
    tok.padding_side = "right"
    quant = None
    if four_bit:
        try:
            quant = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
        except Exception as e:
            print(f"  WARN: bnb 4-bit unavailable ({e}); falling back to bf16 (QLORA-BF16-FALLBACK)")
            quant = None
    model = Gemma4ForCausalLM.from_pretrained(
        BASE,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
        quantization_config=quant,
    )
    model.config.use_cache = False
    raw = load_dataset("json", data_files=SFT_DATA, split="train")
    peft_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none", task_type="CAUSAL_LM",
    )
    cfg = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        bf16=True,
        max_length=512,
        gradient_checkpointing=True,
        optim="adamw_torch",
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        seed=SEED,
    )
    SFTTrainer(
        model=model, args=cfg, train_dataset=raw,
        processing_class=tok, peft_config=peft_config,
    ).train()
    # Save adapter only
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # save_pretrained on a PEFT-wrapped model writes the adapter
    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))


def train_dpo(out_dir: Path, loss_type: str):
    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, Gemma4ForCausalLM
    from trl import DPOConfig, DPOTrainer

    print(f"[dpo:{loss_type}] loading base from {BASE}")
    tok = AutoTokenizer.from_pretrained(BASE)
    tok.padding_side = "left"
    policy = Gemma4ForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    policy.config.use_cache = False
    ref = Gemma4ForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    raw = load_dataset("json", data_files=DPO_DATA, split="train")
    cfg = DPOConfig(
        output_dir=str(out_dir),
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=5e-7,
        beta=0.1,
        loss_type=loss_type,
        bf16=True,
        max_length=512,
        gradient_checkpointing=True,
        optim="adamw_torch",
        precompute_ref_log_probs=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        sync_ref_model=False,
        seed=SEED,
    )
    DPOTrainer(
        model=policy, ref_model=ref, args=cfg,
        train_dataset=raw, processing_class=tok,
    ).train()
    policy.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))


def train_kto(out_dir: Path):
    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, Gemma4ForCausalLM
    from trl import KTOConfig, KTOTrainer

    print(f"[kto] loading base from {BASE}")
    tok = AutoTokenizer.from_pretrained(BASE)
    tok.padding_side = "left"
    policy = Gemma4ForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    policy.config.use_cache = False
    ref = Gemma4ForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    raw = load_dataset("json", data_files=KTO_DATA, split="train")
    cfg = KTOConfig(
        output_dir=str(out_dir),
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=5e-7,
        beta=0.1,
        bf16=True,
        max_length=512,
        gradient_checkpointing=True,
        optim="adamw_torch",
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        seed=SEED,
    )
    KTOTrainer(
        model=policy, ref_model=ref, args=cfg,
        train_dataset=raw, processing_class=tok,
    ).train()
    policy.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))


METHODS = {
    # baselines
    "sft":      ("v4-sft",      lambda d: train_sft(d)),
    "lora":     ("v4-lora",     lambda d: train_lora(d, four_bit=False)),
    "qlora":    ("v4-qlora",    lambda d: train_lora(d, four_bit=True)),
    # DPO + modern preference variants (all via TRL DPOTrainer loss_type)
    "dpo":      ("v4-dpo",      lambda d: train_dpo(d, loss_type="sigmoid")),     # Rafailov 2023 canonical
    "ipo":      ("v4-ipo",      lambda d: train_dpo(d, loss_type="ipo")),         # Azar 2023, fixes overoptimization
    "apo_zero": ("v4-apo-zero", lambda d: train_dpo(d, loss_type="apo_zero")),    # Pan 2024, anchored PO
    "sppo":     ("v4-sppo",     lambda d: train_dpo(d, loss_type="sppo_hard")),   # Wu 2024, self-play PO
    "nca":      ("v4-nca",      lambda d: train_dpo(d, loss_type="nca_pair")),    # Chen 2024, noise-contrastive alignment
    # KTO uses its own trainer (handles unpaired prompt+completion+label)
    "kto":      ("v4-kto",      lambda d: train_kto(d)),                          # Ethayarajh 2024
}


def main():
    method = sys.argv[1] if len(sys.argv) > 1 else "all"
    derive_sft_data()
    derive_kto_data()

    methods_to_run = list(METHODS) if method == "all" else [method]
    for m in methods_to_run:
        if m not in METHODS:
            print(f"unknown method: {m}; choices: {list(METHODS)}")
            sys.exit(1)
        out_subdir, fn = METHODS[m]
        out = OUT_ROOT / out_subdir
        if out.exists() and any(out.iterdir()):
            print(f"\n[{m}] {out} already populated; skipping (delete to re-run)")
            continue
        print(f"\n{'='*70}\n[{m}] starting → {out}\n{'='*70}")
        t0 = time.time()
        try:
            fn(out)
            dt = time.time() - t0
            print(f"[{m}] done in {dt/60:.1f} min")
        except Exception as e:
            dt = time.time() - t0
            print(f"[{m}] FAILED after {dt/60:.1f} min: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
