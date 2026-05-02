"""
DPO Training Script — Direct Preference Optimization for Canvas Item Reranker

Implements the DPO objective from Rafailov et al. 2023, Equation 7:
  L_DPO(π_θ; π_ref) = -E[(x,y_w,y_l)~D] [log σ(
      β log(π_θ(y_w|x)/π_ref(y_w|x)) − β log(π_θ(y_l|x)/π_ref(y_l|x))
  )]
where β=0.1, π_ref = SFT checkpoint (Phase 02), per D-01.
Loss type: sigmoid (TRL DPOConfig default, verified at dpo_trainer.py:1244).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

SFT_CHECKPOINT_PATH = os.environ.get(
    "DPO_SFT_CHECKPOINT",
    "/tmp/canvas-review/GemmaReranker/outputs/sft-checkpoint",
)
DPO_OUTPUT_DIR = "./checkpoints/dpo-checkpoint"
DATA_PATH = "./data/dpo_train.jsonl"


def _bnb_cuda_functional() -> bool:
    # bnb 0.49.2 on CUDA 13.1 (NVIDIA 26.02): no prebuilt binary.
    # Installs ErrorHandlerMockBNBNativeLibrary — lib is not None but unusable.
    try:
        import bitsandbytes.cextension as _ext
        return _ext.lib is not None and "Error" not in type(_ext.lib).__name__
    except Exception:
        return False


def build_tokenizer(sft_path: str):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(sft_path)
    tokenizer.padding_side = "left"
    return tokenizer


def build_dpo_config(output_dir: str, optim: str = "paged_adamw_8bit"):
    from trl import DPOConfig

    return DPOConfig(
        output_dir=output_dir,
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=5e-7,
        beta=0.1,
        loss_type="sigmoid",
        bf16=True,
        max_length=512,
        gradient_checkpointing=True,
        optim=optim,
        precompute_ref_log_probs=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        sync_ref_model=False,
    )


def build_models(sft_path: str):
    import torch
    from transformers import Gemma4ForCausalLM

    policy_model = Gemma4ForCausalLM.from_pretrained(
        sft_path,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    ref_model = Gemma4ForCausalLM.from_pretrained(
        sft_path,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    return policy_model, ref_model


def main():
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

    import torch
    from datasets import load_dataset
    from trl import DPOTrainer
    from training_logger import TrainingLogger, TRLCallbackAdapter

    from callbacks import RewardCollapseCallback
    from data_utils import oversample_hard_negatives

    sft_path = os.environ.get("DPO_SFT_CHECKPOINT", SFT_CHECKPOINT_PATH)

    force_torch = os.environ.get("DPO_FORCE_ADAMW_TORCH", "0") == "1"
    bnb_ok = (not force_torch) and _bnb_cuda_functional()
    optim = "paged_adamw_8bit" if bnb_ok else "adamw_torch"
    if not bnb_ok:
        reason = "DPO_FORCE_ADAMW_TORCH=1" if force_torch else "bitsandbytes CUDA unavailable"
        print(f"WARNING: {reason}; using adamw_torch optimizer (DPO-ADAMW-FALLBACK)", flush=True)

    dpo_config = build_dpo_config(DPO_OUTPUT_DIR, optim=optim)

    run_config = {
        "model": sft_path,
        "method": "dpo",
        "beta": 0.1,
        "lr": 5e-7,
        "epochs": 1,
        "batch_size": 2,
        "grad_accum": 8,
        "max_seq_len": 512,
        "loss_type": "sigmoid",
        "optim": optim,
        "optim_fallback": not bnb_ok,
        "precompute_ref_log_probs": True,
        "bf16": True,
    }

    Path(DPO_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    with TrainingLogger(
        run_name="dpo-run",
        output_dir=DPO_OUTPUT_DIR,
        method="dpo",
        config=run_config,
        verbose=True,
        capture_env=True,
        jsonl_events=True,
        color=True,
    ) as log:
        log.section("SETUP")

        tokenizer = build_tokenizer(sft_path)
        log.log_tokenizer_load(tokenizer)
        log.assert_invariant(
            tokenizer.padding_side == "left",
            "tokenizer.padding_side must be left for DPO training (D-06)",
        )

        policy_model, ref_model = build_models(sft_path)
        policy_model.config.use_cache = False
        log.log_model_load(sft_path, policy_model, torch.bfloat16, "auto")
        log.log_model_load(sft_path, ref_model, torch.bfloat16, "auto")

        raw_dataset = load_dataset("json", data_files=DATA_PATH, split="train")
        dataset = oversample_hard_negatives(raw_dataset, multiplier=3)
        log.log_dataset_load(dataset, "train (oversampled)")
        log.log_training_args(dpo_config)

        trainer = DPOTrainer(
            model=policy_model,
            ref_model=ref_model,
            args=dpo_config,
            train_dataset=dataset,
            processing_class=tokenizer,
            callbacks=[RewardCollapseCallback(), TRLCallbackAdapter(log)],
        )

        log.section("TRAINING")
        trainer.train()

        log.section("SAVE")
        trainer.save_model(DPO_OUTPUT_DIR)
        tokenizer.save_pretrained(DPO_OUTPUT_DIR)
        log.register_checkpoint(DPO_OUTPUT_DIR)


if __name__ == "__main__":
    main()
