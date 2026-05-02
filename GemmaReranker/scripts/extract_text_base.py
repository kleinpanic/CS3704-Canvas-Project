"""
extract_text_base.py — recreate the gemma4-text-base checkpoint
that was lost in the 2026-05-01 /tmp wipe.

Background: google/gemma-4-E2B-it is published as
Gemma4ForConditionalGeneration (a multimodal model) whose text-tower
weights live under the prefix `model.language_model.*`. Loading it
via Gemma4ForCausalLM.from_pretrained() silently random-inits any
keys that don't match (HF loader behavior), which produces the
12.499 ≈ ln(262144) starting-loss bug documented in paper §6.5.

This script remaps the 541 text-tower keys
(model.language_model.* → model.*) and saves a standalone
Gemma4ForCausalLM checkpoint that loads cleanly. Output goes to
checkpoints/gemma4-text-base/ (~18 GiB safetensors).

Verification: post-extraction, Gemma4ForCausalLM.from_pretrained
on this directory should produce a model whose
embed_tokens.weight has σ ≈ 0.031 (pretrained distribution) rather
than σ = 0.02 (random init). SFT step-0 loss should be ≈ 2.5 not
12.499.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

OUT_DIR = Path("checkpoints/gemma4-text-base")
SOURCE_REPO = "google/gemma-4-E2B-it"


def main():
    import torch
    from transformers import AutoConfig, AutoTokenizer
    from huggingface_hub import snapshot_download

    print(f"[1/5] Downloading source checkpoint {SOURCE_REPO} ...")
    src_dir = snapshot_download(SOURCE_REPO)
    print(f"      cached at {src_dir}")

    print(f"[2/5] Loading source weights via safetensors ...")
    from safetensors.torch import load_file, save_file
    weight_files = sorted(Path(src_dir).glob("model-*.safetensors"))
    if not weight_files:
        weight_files = [Path(src_dir) / "model.safetensors"]
    all_weights: dict[str, torch.Tensor] = {}
    for wf in weight_files:
        all_weights.update(load_file(str(wf)))
    print(f"      loaded {len(all_weights)} tensors from {len(weight_files)} shard(s)")

    print(f"[3/5] Remapping text-tower keys (model.language_model.* → model.*) ...")
    remapped: dict[str, torch.Tensor] = {}
    n_remapped = 0
    n_dropped = 0
    for k, v in all_weights.items():
        if k.startswith("model.language_model."):
            new_k = "model." + k[len("model.language_model.") :]
            remapped[new_k] = v
            n_remapped += 1
        elif k.startswith("model.vision_tower.") or k.startswith("model.audio_tower.") or k.startswith("model.multi_modal_projector."):
            n_dropped += 1
        elif k.startswith("model.") or k == "lm_head.weight":
            remapped[k] = v
        else:
            n_dropped += 1
    print(f"      remapped {n_remapped} keys, dropped {n_dropped} vision/audio keys")

    print(f"[4/5] Loading tokenizer + config ...")
    cfg = AutoConfig.from_pretrained(src_dir)
    text_cfg = cfg.text_config if hasattr(cfg, "text_config") else cfg
    text_cfg.architectures = ["Gemma4ForCausalLM"]
    text_cfg.model_type = "gemma4_text"

    tokenizer = AutoTokenizer.from_pretrained(src_dir)

    print(f"[5/5] Writing to {OUT_DIR} ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    save_file(remapped, str(OUT_DIR / "model.safetensors"))
    text_cfg.save_pretrained(str(OUT_DIR))
    tokenizer.save_pretrained(str(OUT_DIR))
    for fname in ("chat_template.jinja", "generation_config.json"):
        src = Path(src_dir) / fname
        if src.exists():
            shutil.copy(src, OUT_DIR / fname)

    print(f"\n[verify] sanity-check load")
    from transformers import Gemma4ForCausalLM
    m = Gemma4ForCausalLM.from_pretrained(str(OUT_DIR), torch_dtype=torch.bfloat16)
    embed = m.model.embed_tokens.weight
    sigma = embed.float().std().item()
    print(f"  embed_tokens.weight sigma = {sigma:.4f}  (target ~0.031, random init = 0.02)")
    if sigma < 0.025:
        print("  WARN: sigma suggests random init — extraction failed")
    else:
        print("  OK: sigma in pretrained range")


if __name__ == "__main__":
    main()
