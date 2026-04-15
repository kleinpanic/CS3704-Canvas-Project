# Gemma 2B Reranker — Phase 1 Research

## What We Already Have

### Data Generation Pipeline (`scripts/generate_rerank_data.py` — 787 lines, committed)
- **Input**: Live Canvas API via `~/.openclaw/hooks/canvas-api.sh`, or `--sample` mode
- **Output format** (JSONL, pairwise):
  ```
  {query, item_a{...serialized info...}, item_b{...}, preference: 1|0|-1,
   urgency_a, urgency_b, reason, pair_type, difficulty, signals}
  ```
- **Urgency formula** (5 weighted signals):
  - `W_TIME=3.0` — hours until due (non-linear: overdue gets +10 to +30 boost)
  - `W_TYPE=2.5` — exam>quiz>assignment>discussion>event>announcement
  - `W_POINTS=1.5` — points/25 (capped at 8)
  - `W_STATUS=2.0` — missing>+15, late>+7, none>0, submitted>-60
  - `W_GRADE_IMPACT=2.0` — based on course weight × (100-current_score)
- **Pair types**: standard, equivalence (near-ties = hard negatives), contrast (top vs bottom), same-course, cross-course
- **Query types**: 17 query templates ("what's due today", "highest value", "grade impact", etc.)
- **Sample data**: 15 realistic Canvas items seeded with Klein's actual grades

### Fine-tune Script (`scripts/finetune_reranker.py` — updated to Gemma 2B)
- Brev instance lifecycle (setup/train/download/teardown)
- Calls `scripts/finetune_gemma.sh` for the actual training
- `LORA_RANK=8, LORA_ALPHA=16, DROPOUT=0.05`
- `BATCH_SIZE=4, GRAD_ACCUM=4, LR=2e-4, EPOCHS=3, MAX_SEQ=256`

---

## Model: google/gemma-2b-it
- 2B decoder-only transformer, instruction-tuned
- Available: BF16, FP16, 4-bit NF4 (via bitsandbytes)
- **Requires**: HuggingFace token +_acceptanta form (one-time at hf.co/settings)

---

## Fine-Tuning Stack

### Libraries
| Library | Purpose | Version |
|---------|---------|---------|
| `transformers` | Model loading + tokenizer | >=4.46 |
| `peft` | LoRA config + adapter management | >=0.13 |
| `bitsandbytes` | 4-bit NF4 quantization | >=0.44 |
| `accelerate` | Distributed launch | >=0.34 |
| `trl` | SFTTrainer wrapper | >=0.12 |
| `datasets` | Data loading | >=3.0 |
| `torch` | Backend | >=2.4 |
| `huggingface_hub` | Model downloads | >=0.26 |

### QLoRA Config
```python
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)
lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj","k_proj","v_proj","o_proj",
                    "gate_proj","up_proj","down_proj"],
    task_type="CAUSAL_LM",
    lora_dropout=0.05,
)
```

### Unsloth (Optional — 2.4x speedup, 58% less VRAM)
```bash
pip install unsloth
# Installs compatible torch, xformers, triton, bitsandbytes, trl, peft
```
**Note**: Unsloth pins its own versions — may conflict with system packages. Use a dedicated venv or Docker layer.

---

## CUDA + GPU Requirements

| GPU | VRAM | Can Run Gemma 2B QLoRA? | Notes |
|-----|------|--------------------------|-------|
| L4 | 22GB | ✅ Yes, comfortable | **Recommended dev GPU** |
| A6000 | 48GB | ✅ Yes, very comfortable | Best bang/buck at $0.60/hr on Brev |
| RTX 5090 | 32GB | ✅ Yes | Consumer, cutting-edge, $0.78/hr Brev |
| A4000 | 16GB | ⚠️ Risky | May OOM on batch 4 with long sequences |
| L40S | 45GB | ✅ Yes | Overkill, $2.23/hr |

**CUDA minimum**: 11.8 (for NF4), recommended 12.4
**Driver**: 525+ on host

---

## Brev Options (Updated)

| Type | Provider | GPU | VRAM | $/hr | Notes |
|------|---------|-----|------|------|-------|
| `g6.xlarge` | AWS | L4 | 22GB | $0.97 | **Dev/fast iteration** |
| `excesssupply_RTX5090` | Excess Supply | RTX 5090 | 32GB | $0.78 | **Production training** |
| `hyperstack_A6000` | Hyperstack | A6000 | 48GB | $0.60 | Best for large batches |
| `g6e.xlarge` | AWS | L40S | 45GB | $2.23 | Overkill |

---

## Docker Setup

### Recommended Base Images

**Option A — PyTorch Official (simplest)**
```dockerfile
FROM pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime
WORKDIR /workspace
```

**Option B — NVIDIA CUDA + manual install (more control)**
```dockerfile
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3.10 python3-pip git curl
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
RUN pip install transformers peft bitsandbytes accelerate datasets huggingface_hub trl
WORKDIR /workspace
```

### Key Docker Decisions
- **CUDA 12.4**: Works on L4, RTX 5090, A6000, A4000, L40S
- **No Unsloth in Docker**: Unsloth requires a bare-metal install (triton kernel compilation). Better to run Unsloth locally on a persistent Brev instance, not in Docker.
- **Volume mounts**: Code, data, and model weights should be mounted, not baked in
- **GGUF export**: Done via llama.cpp inside the same container

---

## GGUF Export Pipeline

After fine-tuning, export for CPU inference:

### Option A — llama.cpp (recommended)
```bash
# Inside Docker or on Brev instance:
# 1. Clone llama.cpp
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake . -DLLAMA_CUBLAS=ON  # for GPU support
make -j$(nproc)

# 2. Convert + quantize
python3 convert_hf_to_gguf.py /path/to/outputs/gemma-2b-reranker --outfile gemma-2b-reranker-F16.gguf
./quantize gemma-2b-reranker-F16.gguf gemma-2b-reranker-Q4_K_M.gguf Q4_K_M
```

### Option B — Unsloth export (if training with Unsloth)
```python
from unsloth import FastLanguageModel
FastLanguageModel.export_as_gguf("gemma-2b-reranker", quantized=True)
```

### GGUF Inference in Canvas TUI
- llama.cpp bindings (`llama-cpp-python`) for local CPU inference
- Or keep GPU inference (gemma-2b Q4_K_M at ~1.5GB fits in any modern GPU)

---

## Open Questions

### 1. Training Data Format for Gemma 2B
The existing `generate_rerank_data.py` outputs:
```
{query, item_a{serialized:"[ASGN] Homework 4... Due Today... 100pts MISSING"}, 
 item_b{...}, preference: 1, urgency_a: 52.3, urgency_b: 21.1, reason:"...", ...}
```
Gemma 2B expects CAUSAL_LM format — we need to format this as:
```
[query]: what's due today
Item A: [ASGN] Homework 4 — CS 2505 — Due Today — 100pts — MISSING
Item B: [QUIZ] NEUR Quiz 2 — NEUR 2464 — Tomorrow — 25pts — LATE
Which is more urgent? Item A is more urgent.
```
This goes into the TRL/SFTTrainer as a text field.

### 2. Canvas Items Available
Currently **12 assignment items** in Spring 2026 Canvas across 6 courses.
With the 17 query templates × 5 pair types, this generates ~80-150 unique pairs 
from live data. The script also supports hard negatives and augmented synthetic data.
**Question**: Is this enough for meaningful fine-tuning, or do we need more?

### 3. Unsloth vs Standard PEFT
- Standard (`peft`+`bitsandbytes`): ~2-3 hours on L4, well-understood
- Unsloth: ~45 min on L4, but pinned dependencies
**Recommendation**: Start with standard PEFT for reproducibility. Add Unsloth in phase 2 if speed matters.

### 4. GGUF for Canvas TUI
Do we need GGUF output for local CPU inference, or is GPU-at-inference acceptable?
- **GGUF**: Can run on CPU (no GPU needed at inference time), ~1.5GB for Q4_K_M
- **GPU**: Faster, but requires GPU at runtime. Canvas TUI on broklein has no GPU.
- **Decision needed**: Is this for local Canvas TUI use, or just a demo?

### 5. Brev Instance Strategy
- **Persistent dev box** ($0.60-0.97/hr): Keep A6000 or L4 running for iteration
- **Ephemeral training run**: Spin up, train, save artifacts, spin down
- **Recommendation**: Persistent dev box for iteration, ephemeral for final training run
