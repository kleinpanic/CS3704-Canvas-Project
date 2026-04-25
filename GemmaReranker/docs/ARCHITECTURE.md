# GemmaReranker — Architecture & Setup Plan
**Project:** Canvas Deadline Tracker Priority Reranker (DPO Training)
**Location:** `~/codeWS/Python/CS3704-Canvas-Project/GemmaReranker/`
**Stage:** Planning — research and documentation complete, execution pending Klein approval

---

## 1. Problem Statement

Our DPO reranker training pipeline failed because:
1. The dataset has contaminated train/test splits (item-level leakage) and only 1 user's data
2. The Gemma 4B student model had a HuggingFace gate issue
3. Scripts weren't synced to Spark
4. No self-contained project structure for teammate onboarding

This plan addresses all four.

---

## 2. System Context — What Exists on Spark

### Spark AI Stack (`/srv/spark-ai-v2/`)

| Component | Location | Purpose |
|----------|----------|---------|
| Manager V2 | `manager-v2/` | Control plane — slot lifecycle, routing, health |
| Proxy | `spark-proxy` container | Smart router, auth, OpenAI-compatible API |
| Production Slot | `spark-vllm-slot0` | Nemotron-3-Super-120B-NVFP4, always-on |
| TRT-LLM Slot | `spark-trtllm-slot0` | TensorRT-LLM for NVFP4 models (pre-pulled, 29GB) |
| Services | `compose.Services.yaml` | spark-reranker, spark-stt, spark-tts, etc. |
| Forge CLI | `forge` | Only-authorized interface for all stack operations |

### Hardware
- **GPU:** 4×H100 80GB (Blackwell GB10)
- **vRAM available:** ~320GB total; slot0 uses ~67GB (Nemotron @ gpu_util=0.89)
- **Free for training:** ~250GB if slot0 is not maxed

### Resource Defense Layers (must respect)
| Layer | Mechanism | Critical values |
|-------|-----------|----------------|
| Kernel | `vm.min_free_kbytes=524288` | Swap-protected |
| earlyoom | SIGTERM @ mem≤3%, SIGKILL @ mem≤1% | protects manager/proxy |
| Per-container | `oom_score_adj` | slot0=+500 (dies first), manager=-500, proxy=-700 |
| Health watchdog | SBSA `/dev/watchdog0`, 10s timeout | |

### Gemma Model Specs
| Model | Format | vRAM @ fp16 | vRAM @ NVFP4 | Context | Notes |
|-------|--------|-------------|--------------|---------|-------|
| Gemma-4-31B-IT | NVFP4 (Blackwell) | ~62GB | ~31GB @ gpu_util=0.40 | 256K | Must use vLLM |
| Gemma-4-2B-IT | FP16/BF16 | ~4GB | N/A (not NVFP4) | 128K | QLoRA 4-bit: ~2GB |

---

## 3. Planned Architecture

### 3.1 Docker Compose Structure

```
GemmaReranker/
├── docker/
│   ├── compose.teacher.yaml    # vLLM slot for Gemma-4-31B (teacher)
│   ├── compose.student.yaml     # vLLM slot for Gemma-4-2B (student inference)
│   └── compose.trainer.yaml    # DPO training container (PyTorch + TRL)
└── configs/
    ├── teacher.slot.env         # ENV for teacher vLLM slot
    ├── student.slot.env         # ENV for student vLLM slot
    └── trainer.venv.env         # ENV for training venv setup
```

**Design principle:** Follow the exact same pattern as `compose.Services.yaml` and `compose.LLM.yaml` from spark-ai-v2. Do NOT modify any spark-ai-v2 files.

### 3.2 Teacher Slot (Gemma-4-31B-IT-NVFP4)

```yaml
# compose.teacher.yaml
services:
  gemma-reranker-teacher:
    image: vllm/vllm-openai:gemma4-cu130
    container_name: gemma-reranker-teacher
    mem_limit: 72g                    # Hard ceiling — prevents OOM cascade
    restart: "no"                      # Manual lifecycle only
    shm_size: 16g
    environment:
      HF_TOKEN: ${HF_TOKEN}
      VLLM_WORKER_MULTIPROC_METHOD: spawn
    volumes:
      - hf-cache:/root/.cache/huggingface
      - ./data:/app/data:ro
    networks:
      - spark-net
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    oom_score_adj: 200                # Dies before manager, after slot0
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]
      interval: 30s; timeout: 10s; retries: 3; start_period: 360s
    command: >
      sh -c "vllm serve nvidia/Gemma-4-31B-IT-NVFP4
        --port 8000 --host 0.0.0.0
        --max-model-len 262144
        --max-num-seqs 64
        --gpu-memory-utilization 0.40
        --kv-cache-dtype fp8
        --quantization modelopt
        --enable-chunked-prefill
        --enable-prefix-caching
        --trust-remote-code
        --tensor-parallel-size 1
        --pipeline-parallel-size 1"
```

### 3.3 Student Slot (Gemma-4-2B-IT — for Path B inference)

```yaml
# compose.student.yaml
services:
  gemma-reranker-student:
    image: vllm/vllm-openai:latest
    container_name: gemma-reranker-student
    mem_limit: 8g
    restart: "no"
    shm_size: 4g
    environment:
      HF_TOKEN: ${HF_TOKEN}
      VLLM_WORKER_MULTIPROC_METHOD: spawn
    volumes:
      - hf-cache:/root/.cache/huggingface
    networks:
      - spark-net
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    oom_score_adj: 250
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health')"]
      interval: 30s; timeout: 10s; retries: 3; start_period: 120s
    command: >
      sh -c "vllm serve google/Gemma-4-2B-IT
        --port 8001 --host 0.0.0.0
        --max-model-len 131072
        --max-num-seqs 256
        --gpu-memory-utilization 0.60
        --trust-remote-code
        --tensor-parallel-size 1
        --quantization fp8"
```

### 3.4 Training Container (DPO via TRL)

```yaml
# compose.trainer.yaml
services:
  gemma-reranker-trainer:
    image: nvcr.io/nvidia/pytorch:25.11-py3
    container_name: gemma-reranker-trainer
    mem_limit: 64g
    restart: "no"
    shm_size: 8g
    ipc: host                          # Required for NCCL shared memory
    environment:
      HF_TOKEN: ${HF_TOKEN}
      CUDA_VISIBLE_DEVICES: "0"
    volumes:
      - hf-cache:/root/.cache/huggingface
      - ../../GemmaReranker:/workspace:rw
    working_dir: /workspace
    networks:
      - spark-net
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    oom_score_adj: 300
    command: ["python3", "/workspace/scripts/run_pipeline.py", "--path", "b", "--teacher-url", "http://gemma-reranker-teacher:8000/v1"]
```

**Note on TRL + vLLM vs. native HF:** The playbook's `nvidia/pytorch-fine-tune` approach uses direct `transformers + peft + trl` inside the container. This is what our `scripts/run_pipeline.py` already does. No LLaMA Factory needed.

---

## 4. Orchestration

### 4.1 Slot Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                      SPARK SLOTS                             │
│  slot0 (Nemotron) ──── always on, DO NOT TOUCH             │
│                                                             │
│  gemma-reranker-teacher ── started before Path B            │
│    → uses vLLM on Blackwell NVFP4 format                   │
│    → http://gemma-reranker-teacher:8000/v1                  │
│                                                             │
│  gemma-reranker-student ── student inference (Path B step 2)│
│    → google/Gemma-4-2B-IT loaded on same or second GPU      │
│    → http://gemma-reranker-student:8001/v1                  │
│                                                             │
│  gemma-reranker-trainer ── runs run_pipeline.py Path B      │
│    → calls teacher at :8000, student at :8001              │
│    → writes checkpoints to /srv/spark-maker/output/         │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Startup Sequence (per Path B run)

```bash
# 1. Ensure slot0 is healthy (Nemotron running)
forge list | grep slot0

# 2. Start teacher slot (Gemma-4-31B — ~15min cold load)
docker compose -f compose.teacher.yaml up -d
# Wait: curl http://localhost:8000/health → "OK"

# 3. Start student slot (Gemma-4-2B — ~2min)
docker compose -f compose.student.yaml up -d
# Wait: curl http://localhost:8001/health → "OK"

# 4. Verify teacher can label pairs
curl http://localhost:8000/v1/models  # confirm Gemma-4-31B loaded

# 5. Run Path B training (hours)
docker compose -f compose.trainer.yaml up --rm gemma-reranker-trainer

# 6. Tear down slots
docker compose -f compose.teacher.yaml down
docker compose -f compose.student.yaml down
```

### 4.3 Resource Budget (worst case — both slots + trainer)

| Component | vRAM | Mem limit | Notes |
|-----------|------|-----------|-------|
| Nemotron (slot0) | ~67GB | — | existing, untouched |
| Teacher (31B NVFP4) | ~31GB | 72GB | gpu_util=0.40 |
| Student (2B FP8) | ~4GB | 8GB | shared GPU possible |
| Trainer (gradients) | ~8GB | 64GB | separate container |
| **Total** | **~110GB** | 144GB | Fits in 320GB |

---

## 5. Scripts Structure (self-contained)

```
GemmaReranker/
├── scripts/
│   ├── run_pipeline.py          # Unified pipeline (Path A + Path B)
│   ├── generate_rerank_data.py  # Single-user pairwise data generation
│   ├── collect_rerank_dataset.py # Multi-user merge + anonymize + split
│   ├── benchmark.py             # Heuristic vs adapter benchmark
│   └── path_b_tui.py            # Spark TUI for Path B orchestration
├── data/
│   ├── collab/                  # Teammate contributions (PRIVATE, .gitignore)
│   ├── rerank_train.jsonl        # Training set (generated)
│   ├── rerank_test.jsonl         # Test set (generated)
│   └── rerank_merged.jsonl       # Merged before split
├── docker/
│   ├── compose.teacher.yaml
│   ├── compose.student.yaml
│   ├── compose.trainer.yaml
│   └── docker.mkdocs.yml         # Aggregates all three
└── docs/
    ├── ARCHITECTURE.md           # This file
    ├── SETUP.md                  # Step-by-step execution guide
    ├── DATASET.md                # Teammate contribution workflow
    └── SPARK.md                  # Spark-specific notes
```

All scripts are copied from the main repo and updated to be fully self-contained with relative paths inside `GemmaReranker/`.

---

## 6. Teammate Onboarding

Each teammate runs:
```bash
# 1. Clone repo
git clone https://github.com/kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project/GemmaReranker

# 2. Set up environment
cp configs/teammate.env.example .env
# Edit .env: CANVAS_TOKEN=vt_xxx, HF_TOKEN=hf_xxx, YOUR_HANDLE=alice

# 3. Generate data (5 min, their Canvas token)
python scripts/generate_rerank_data.py \
  --token $CANVAS_TOKEN \
  --handle $YOUR_HANDLE \
  --output data/collab/${YOUR_HANDLE}_anon.jsonl

# 4. Submit PR with their anonymized file
git checkout -b data/${YOUR_HANDLE}
git add data/collab/${YOUR_HANDLE}_anon.jsonl
git commit -m "data: add anonymized rerank dataset from ${YOUR_HANDLE}"
gh pr create --title "Dataset: ${YOUR_HANDLE} contribution"
```

The merge + clean + split happens in `collect_rerank_dataset.py` on the repo owner's side.

---

## 7. Known Issues & Mitigations

| Issue | Mitigation |
|-------|-----------|
| Dataset contamination (item-level) | Use `collect_rerank_dataset.py --split items` — enforces item-ID-level split |
| Single-user bias | Require 3+ teammates before running Path B |
| Teacher model gate (HF_TOKEN) | Already accepted per Klein; verify `HF_TOKEN` in `.env` |
| OOM cascade | `mem_limit` on all containers; `oom_score_adj` hierarchy preserved |
| Long cold-start for Gemma-4-31B | Pre-warm slot before training run (healthcheck start_period: 360s) |
| Path B TUI needs `--teacher-url` | Update `run_pipeline.py` to accept `--teacher-url` for Docker networking |

---

## 8. References

- Spark AI V2 Architecture: `/srv/spark-ai-v2/ARCHITECTURE.md`
- Slot Spec V2: `/srv/spark-ai-v2/docs/SLOT-SPEC-V2.md`
- DGX Spark Playbooks: `/srv/spark-maker/playbooks/dgx-spark-playbooks/nvidia/`
- NeMo Fine-Tune Playbook: `nvidia/nemo-fine-tune/` (PyTorch + PEFT approach)
- PyTorch Fine-Tune Playbook: `nvidia/pytorch-fine-tune/` (venv-based TRL approach)
- DPO Paper: `https://arxiv.org/pdf/2305.18290`
- Attention Is All You Need: `https://arxiv.org/pdf/1706.03762`
