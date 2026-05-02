#!/usr/bin/env python3
"""
export_gguf.py — Merge QLoRA adapter into base model, export to Q5_K_M GGUF.

Steps:
  1. Load base model (google/gemma-4-E2B-it) in BF16
  2. Load QLoRA adapter and merge via PEFT merge_and_unload()
  3. Save merged BF16 checkpoint to disk
  4. Convert to F16 GGUF using llama.cpp convert_hf_to_gguf.py
  5. Quantize F16 GGUF to Q5_K_M using llama-quantize

Usage (inside training container or on host with transformers + peft):
  python source/export_gguf.py

Environment:
  GGUF_ADAPTER     — path to QLoRA adapter dir (default: /tmp/canvas-review/GemmaReranker/outputs/qlora-adapter)
  GGUF_BASE_MODEL  — HF model ID (default: google/gemma-4-E2B-it)
  GGUF_OUTPUT_DIR  — output directory (default: ./checkpoints/gguf)
  LLAMA_CPP_DIR    — path to llama.cpp source (default: ~/.local/srcs/gitclones/llama.cpp)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoTokenizer, Gemma4ForCausalLM

ADAPTER_PATH = os.environ.get(
    "GGUF_ADAPTER",
    "/tmp/canvas-review/GemmaReranker/outputs/qlora-adapter",
)
BASE_MODEL = os.environ.get(
    "GGUF_BASE_MODEL",
    "/tmp/canvas-review/GemmaReranker/outputs/gemma4-text-base",
)
OUTPUT_DIR = Path(os.environ.get("GGUF_OUTPUT_DIR", "./checkpoints/gguf"))
LLAMA_CPP = Path(os.environ.get(
    "LLAMA_CPP_DIR",
    Path.home() / ".local/srcs/gitclones/llama.cpp",
))

MERGED_DIR = OUTPUT_DIR / "merged_bf16"
F16_GGUF = OUTPUT_DIR / "gemma4-reranker-f16.gguf"
Q5_GGUF = OUTPUT_DIR / "gemma4-reranker-Q5_K_M.gguf"


def step1_merge(adapter_path: str, base_model: str) -> None:
    print(f"[1/4] Loading base model {base_model} ...")
    model = Gemma4ForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
        device_map="cpu",
    )
    print(f"[2/4] Loading and merging adapter {adapter_path} ...")
    model = PeftModel.from_pretrained(model, adapter_path)
    merged = model.merge_and_unload()

    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[3/4] Saving merged BF16 checkpoint → {MERGED_DIR} ...")
    merged.save_pretrained(str(MERGED_DIR))
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    tokenizer.save_pretrained(str(MERGED_DIR))
    print(f"      Saved.")


def step2_convert() -> None:
    convert_script = LLAMA_CPP / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        sys.exit(f"ERROR: llama.cpp not found at {LLAMA_CPP}. Set LLAMA_CPP_DIR.")

    F16_GGUF.parent.mkdir(parents=True, exist_ok=True)
    print(f"[4a/4] Converting merged BF16 → F16 GGUF ...")
    gguf_py = str(LLAMA_CPP / "gguf-py")
    env = os.environ.copy()
    env["PYTHONPATH"] = gguf_py + ((":" + env["PYTHONPATH"]) if "PYTHONPATH" in env else "")
    cmd = [
        sys.executable, str(convert_script),
        str(MERGED_DIR),
        "--outfile", str(F16_GGUF),
        "--outtype", "f16",
    ]
    print(f"  PYTHONPATH={gguf_py} {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        sys.exit(f"ERROR: GGUF conversion failed (exit {result.returncode})")
    size_mb = F16_GGUF.stat().st_size / 1e6
    print(f"      F16 GGUF: {F16_GGUF} ({size_mb:.0f} MB)")


def step3_quantize() -> None:
    quantize_bin = LLAMA_CPP / "build" / "bin" / "llama-quantize"
    if not quantize_bin.exists():
        sys.exit(
            f"ERROR: llama-quantize not found at {quantize_bin}. "
            "Run: cd ~/.local/srcs/gitclones/llama.cpp && cmake --build build --target llama-quantize"
        )

    print(f"[4b/4] Quantizing F16 GGUF → Q5_K_M ...")
    cmd = [str(quantize_bin), str(F16_GGUF), str(Q5_GGUF), "Q5_K_M"]
    print(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"ERROR: quantization failed (exit {result.returncode})")
    size_mb = Q5_GGUF.stat().st_size / 1e6
    print(f"      Q5_K_M GGUF: {Q5_GGUF} ({size_mb:.0f} MB)")
    if size_mb > 2000:
        print(f"WARNING: GGUF exceeds 2 GB target ({size_mb:.0f} MB)")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Gemma-4 Reranker — QLoRA Merge + GGUF Export")
    print(f"  Adapter:    {ADAPTER_PATH}")
    print(f"  Base model: {BASE_MODEL}")
    print(f"  Output:     {OUTPUT_DIR}")
    print("=" * 60)

    if not MERGED_DIR.exists() or not any(MERGED_DIR.iterdir()):
        step1_merge(ADAPTER_PATH, BASE_MODEL)
    else:
        print(f"[1-3/4] Merged checkpoint already exists at {MERGED_DIR} — skipping merge.")

    if not F16_GGUF.exists():
        step2_convert()
    else:
        print(f"[4a/4] F16 GGUF already exists at {F16_GGUF} — skipping conversion.")

    if not Q5_GGUF.exists():
        step3_quantize()
    else:
        size_mb = Q5_GGUF.stat().st_size / 1e6
        print(f"[4b/4] Q5_K_M GGUF already exists: {Q5_GGUF} ({size_mb:.0f} MB)")

    print("\nDone.")
    print(f"  Q5_K_M GGUF: {Q5_GGUF}")
    print(f"  Size: {Q5_GGUF.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
