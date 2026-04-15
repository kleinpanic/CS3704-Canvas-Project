#!/usr/bin/env python3
"""
Gemma 2B Reranker — LoRA Merge + GGUF Export
==============================================
Merges the QLoRA LoRA adapter into the base Gemma 2B IT weights,
then quantizes to GGUF for use with llama.cpp or ollama.

Usage:
    # Option A: via Spark trainer container (preferred on Spark)
    docker compose run --rm trainer \
        python3 /workspace/scripts/export_gguf.py \
            --adapter /workspace/outputs/gemma2b-reranker \
            --base-model nvidia/Llama-3.1-8B-Instruct-FP4 \
            --output /workspace/gemma2b-reranker/data/gemma-2b-reranker-Q4_K_M.gguf

    # Option B: via Python directly
    python3 scripts/export_gguf.py \
        --adapter ~/codeWS/Gemma2B-Reranker/outputs/gemma2b-reranker \
        --output ~/codeWS/Gemma2B-Reranker/data/gemma-2b-reranker-Q4_K_M.gguf

    # Option C: Docker on any machine
    docker run --gpus all --rm -v $(pwd):/workspace gemma2b-trainer \
        python3 /workspace/scripts/export_gguf.py \
            --adapter /workspace/outputs \
            --output /workspace/data/gemma-2b-reranker-Q4_K_M.gguf

Output:
    gemma-2b-reranker-Q4_K_M.gguf   (~1.3 GB)
    gemma-2b-reranker-Q8_0.gguf    (~2.5 GB, higher quality)
"""

import argparse
import json
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

warnings.filterwarnings("ignore")

BASE_MODEL = "nvidia/Llama-3.1-8B-Instruct-FP4"

# GGUF quantization type → llama.cpp argument
# Q4_K_M: 4-bit with medium quantization — good quality/size tradeoff for reranking
# Q8_0: 8-bit — near-lossless, 2x size
QUANT_TYPES = {
    "Q4_K_M": {},
    "Q8_0":  {},
}


def merge_and_export(
    adapter_path: str,
    base_model: str,
    output_path: str,
    quant_type: str = "Q4_K_M",
):
    p = Path(output_path)
    output_dir = p.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Gemma 2B Reranker — LoRA Merge + GGUF Export")
    print(f"  Adapter:   {adapter_path}")
    print(f"  Base:     {base_model}")
    print(f"  Output:   {output_path}")
    print(f"  Quant:    {quant_type}")
    print("=" * 60)

    # ── Step 1: Merge LoRA into base model ────────────────────────────────────
    print("\n[1/4] Loading base model...")
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb,
        device_map="cpu",         # CPU for merge — we unload after
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    print("[2/4] Loading and merging LoRA adapter...")
    model = PeftModel.from_pretrained(base, adapter_path)
    print("  Merging LoRA weights into base...")
    merged = model.merge_and_unload()
    print(f"  Merged model type: {type(merged).__name__}")

    # ── Step 2: Save merged BF16 checkpoint ──────────────────────────────────
    merged_dir = output_dir / "merged_bf16"
    print(f"\n[3/4] Saving merged BF16 to {merged_dir}...")
    merged.save_pretrained(str(merged_dir))
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    tokenizer.save_pretrained(str(merged_dir))
    print("  Merged checkpoint saved ✓")

    # ── Step 3: Convert to GGUF via llama.cpp python binding ──────────────────
    print(f"\n[4/4] Converting to GGUF ({quant_type})...")
    try:
        from llama_cpp import Llama
        from llama_cpp.llama_grammar import LlamaJSONSchemaGrammar
        print("  llama-cpp-python available ✓")
    except ImportError:
        print("  llama-cpp-python not installed — using convert-hf-to-gguf.py instead")
        # Fall back to official HF convert script
        _convert_via_hf_script(merged_dir, output_path, quant_type)
        return

    # llama-cpp doesn't have a direct "load HF, export GGUF" API.
    # Use the HF convert script approach instead.
    _convert_via_hf_script(merged_dir, output_path, quant_type)


def _convert_via_hf_script(merged_dir: Path, output_path: str, quant_type: str):
    """Use HuggingFace's official convert-hf-to-gguf script."""
    script_url = (
        "https://huggingface.co/ggerganov/llama.cpp/master/convert-hf-to-gguf.py"
    )
    script_path = Path("/tmp/convert-hf-to-gguf.py")
    print(f"  Downloading convert-hf-to-gguf.py...")
    import urllib.request
    urllib.request.urlretrieve(script_url, script_path)

    out_p = Path(output_path)
    cmd = [
        sys.executable, str(script_path),
        str(merged_dir),
        "--outfile", str(out_p),
        "--outtype", quant_type.lower().replace("_", "-"),
    ]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STDOUT: {result.stdout[-500:]}")
        print(f"  STDERR: {result.stderr[-500:]}")
        raise RuntimeError(f"GGUF conversion failed: {result.stderr[-200:]}")
    print(f"\n  ✓ GGUF saved: {out_p} ({out_p.stat().st_size / 1e6:.1f} MB)")


# ── CLI ────────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Merge LoRA + export to GGUF")
    p.add_argument("--adapter", required=True,
                   help="Path to LoRA adapter directory")
    p.add_argument("--base-model", default=BASE_MODEL,
                   help="HF model ID (default: nvidia/Llama-3.1-8B-Instruct-FP4)")
    p.add_argument("--output", required=True,
                   help="Output GGUF file path")
    p.add_argument("--quant", default="Q4_K_M",
                   choices=list(QUANT_TYPES.keys()),
                   help="Quantization type (default: Q4_K_M)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    merge_and_export(
        adapter_path=args.adapter,
        base_model=args.base_model,
        output_path=args.output,
        quant_type=args.quant,
    )
    print("\nDone. Next: deploy GGUF to your inference endpoint or run local eval.")
