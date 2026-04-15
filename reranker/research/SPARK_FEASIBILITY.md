# Gemma 2B Training on Spark DGX GB10 — Feasibility Analysis (v3)

**Date:** 2026-04-15  
**Updated:** Reflects spark-maker (NOT spark-ai-v2) for training  
**Status:** READY TO RUN — scripts committed, data validated locally

---

## Hardware: Spark DGX GB10

| Spec | Value |
|------|-------|
| SoC | NVIDIA GB10 Grace-Blackwell Superchip |
| Memory | **128 GB UMA** — CPU + GPU share the same pool |
| GPU | Integrated Blackwell (not discrete) |
| CPU | ARM Neoverse (Grace), aarch64 |
| Storage | 3.7 TB NVMe, ~2.2 TB used |
| Training stack | `/srv/spark-maker/` — LLaMA-Factory + unsloth + trl + peft |
| Access | `ssh spark` → `forge` CLI + `docker compose` |

**Currently running**: Nemotron-120B in slot0 (~58GB memory used)

---

## Memory Analysis

```
Total memory:           122 GB
├─ Nemotron 120B:       -58 GB  (loaded in slot0)
├─ System + services:   -10 GB
├─ Docker overhead:      -5 GB
└─ Free for training:    ~14 GB  ← Path A fits here
```

**Path A (Direct QLoRA)**: Gemma 2B QLoRA needs ~2-4GB. Fits in 14GB free. Nemotron stays loaded. ✓

**Path B (DPO Distillation)**: Gemma-4-31B (18GB) + training (4GB) = ~22GB. Need to stop Nemotron first.

---

## The Two Paths

### Path A — Direct QLoRA (Start Here)

```
google/gemma-2b-it ──QLoRA──► LoRA adapter
(heuristic labels)
```
- **Time**: 20-40 min on GB10
- **Memory**: ~2-4GB (fits alongside Nemotron)
- **Scripts**: `finetune-lora.sh` on spark-maker
- **Risk**: Low — no model swaps needed

### Path B — Offline DPO Distillation (After A)

```
nvidia/Gemma-4-31B-IT-NVFP4 (teacher)
        │
        │ Load into vLLM (forge load)
        │ Generate 1912 preference explanations
        ▼
{ "prompt": query, "chosen": reason, "rejected": reason }  (DPO JSONL)
        │
        ▼
google/gemma-2b-it (student) ──DPO──► LoRA adapter
```
- **Time**: ~90 min total (load 31B: 5min + generate prefs: 15min + DPO train: 50min)
- **Memory**: ~22GB — MUST stop Nemotron first (`forge unload 0`)
- **Advantage**: Learns *why* items are urgent, not just surface patterns
- **Best for**: Hard negatives (urgency diff < 3.0) where heuristic is uncertain

---

## spark-maker vs spark-ai-v2

| | spark-ai-v2 | spark-maker |
|--|-------------|-------------|
| Purpose | Always-on inference services | On-demand ML toolkit |
| Training | No | **YES** ✓ |
| Trainer container | N/A | `nvcr.io/nvidia/vllm:26.01-py3` + unsloth + trl |
| LLaMA-Factory | No | **YES** ✓ |
| Quantization | No | **YES** (NVFP4, AWQ, GPTQ) |
| CLI | `forge` | `forge` + `docker compose run --rm trainer` |

**Use `spark-maker` for ALL training work.**

---

## Run Commands

### Path A: Direct QLoRA (try now)
```bash
# Copy data
scp ~/codeWS/Gemma2B-Reranker/data/rerank_sft.jsonl spark:/srv/spark-maker/datasets/

# Train (Nemotron stays loaded)
ssh spark
cd /srv/spark-maker
docker compose run --rm trainer \
    bash /workspace/scripts/finetune-lora.sh \
    google/gemma-2b-it \
    /workspace/datasets/rerank_sft.jsonl \
    gemma2b-reranker \
    qlora

# Output: /srv/spark-maker/output/loras/gemma2b-reranker/
```

### Path B: DPO Distillation
```bash
# Stop Nemotron, free 58GB
forge unload 0

# Load teacher
forge load nvidia/Gemma-4-31B-IT-NVFP4 --slot 0

# Generate teacher preferences
ssh spark
cd /srv/spark-maker
docker compose run --rm trainer \
    python3 /workspace/scripts/generate_teacher_preferences.py \
        --input /srv/spark-maker/datasets/rerank_clean.jsonl \
        --output /srv/spark-maker/datasets/rerank_dpo.jsonl \
        --teacher-endpoint http://localhost:8000/v1

# DPO train student
python3 scripts/train_config_gen.py \
    --model google/gemma-2b-it --method dpo \
    --dataset /srv/spark-maker/datasets/rerank_dpo.jsonl \
    --output /srv/spark-maker/configs/generated/gemma2b-dpo.yaml

docker compose run --rm trainer \
    python3 /workspace/LLaMA-Factory/src/train.py \
    /srv/spark-maker/configs/generated/gemma2b-dpo.yaml

# Restart Nemotron
forge load nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4 --slot 0
```

---

## Local Validation (Done ✓)

```
rerank_sft.jsonl: 1912 examples, 797KB
rerank_clean.jsonl: 1912 pairs, balanced A=956/B=956
All scripts: syntax OK
CANVAS_TOKEN: SET
```

Ready to scp + run on spark-maker.
