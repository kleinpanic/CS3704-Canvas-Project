# Gemma 2B Canvas Reranker

Fine-tune Gemma 2B IT as a Canvas item priority reranker using QLoRA + DPO distillation.

## Two Training Paths

| | Path A: Direct QLoRA | Path B: DPO Distillation |
|--|---|---|
| Teacher | None | Gemma-4-31B-IT-NVFP4 |
| Training signal | Heuristic preferences | Synthetic (teacher reasoning) |
| Complexity | Simple | Full TUI pipeline |
| Time on GB10 | 20-40 min | ~90 min |
| Memory | ~2-4GB (fits with Nemotron) | ~22GB (need to unload Nemotron) |
| Quality | Matches heuristic | Better on hard negatives |

**Start with Path A.** Path B adds a teacher model (Gemma-4-31B) that explains *why* one item is more urgent — giving the student model richer training signal.

---

## Quick Start (Path A — 20 min)

```bash
# 1. Copy data to spark-maker
scp ~/codeWS/Gemma2B-Reranker/data/rerank_sft.jsonl \
    spark:/srv/spark-maker/datasets/

# 2. Run QLoRA training (Nemotron stays loaded — fits in 14GB free)
ssh spark
cd /srv/spark-maker
docker compose run --rm trainer \
    bash /workspace/scripts/finetune-lora.sh \
    google/gemma-2b-it \
    /workspace/datasets/rerank_sft.jsonl \
    gemma2b-reranker \
    qlora

# 3. Benchmark
docker compose run --rm trainer \
    python3 /workspace/scripts/benchmark.py \
        --adapter /srv/spark-maker/output/loras/gemma2b-reranker \
        --test /srv/spark-maker/datasets/rerank_test.jsonl \
        --output /srv/spark-maker/output/benchmarks/results.json

# 4. Export GGUF
docker compose run --rm converter \
    bash /workspace/scripts/convert-gguf.sh \
    /srv/spark-maker/output/loras/gemma2b-reranker \
    Q4_K_M

# 5. Copy results home
scp -r spark:/srv/spark-maker/output/ ~/codeWS/Gemma2B-Reranker/outputs/
```

Full commands: see `plans/PLAN.md`

---

## Project Structure

```
Gemma2B-Reranker/
├── research/
│   ├── FLOW.md              ← locked pipeline (READ THIS)
│   ├── PLAN.md              ← step-by-step execution plan
│   ├── SPARK_FEASIBILITY.md ← GB10 memory analysis, Path A/B split
│   ├── BENCHMARK.md         ← 7-benchmark spec with pass/fail bars
│   ├── CLAIMS.md            ← priority algorithm + open questions
│   └── DATASET_TOOLS.md     ← Argilla, HF alignment-handbook, Unsloth
├── data/
│   └── collab/             ← teammates' anonymized JSONL (gitignored)
│       └── rerank_clean.jsonl  ← merged + balanced dataset
│   └── rerank_sft.jsonl     ← SFTTrainer format (797KB, 1912 pairs)
├── scripts/                 ← symlink → CS3704-Canvas-Project/scripts
│   ├── collect_rerank_dataset.py  ← Canvas → pairwise JSONL
│   ├── generate_teacher_preferences.py  ← Path B teacher labeling
│   ├── train_gemma2b.py     ← QLoRA fine-tune (local/Brev)
│   ├── benchmark.py          ← 7-benchmark suite
│   ├── export_gguf.py       ← LoRA merge + GGUF quantize
│   └── path_b_tui.py         ← Path B TUI orchestrator (Textual)
└── docker/
    ├── Dockerfile            ← CUDA 12.4 + HF stack + llama.cpp
    └── run.sh               ← docker helper
```

---

## Collaborative Dataset

**Privacy first** — each teammate generates their own data locally, anonymizes it, then contributes.

See `DATASET_README.md` in the CS3704-Canvas-Project repo for full teammate instructions.

```bash
# Each teammate:
python3 scripts/collect_rerank_dataset.py generate \
    --output data/collab/HANDLE.jsonl --handle HANDLE

# Anonymize BEFORE contributing (REQUIRED)
python3 scripts/collect_rerank_dataset.py anonymize \
    --input data/collab/HANDLE.jsonl \
    --output data/collab/HANDLE_anon.jsonl

# Submit HANDLE_anon.jsonl (NOT the raw file)
```

The anonymizer transforms:
- `CS2505` → `COURSE001`
- "Homework 4 — Managing a Roster" → `Homework`
- `kleinpanic` → `contributor001`
- Absolute due dates → removed

---

## 7 Custom Benchmarks

Standard benchmarks (MMLU, GSM8K, etc.) don't apply — we need to measure Canvas priority accuracy.

| # | Benchmark | Pass bar |
|---|-----------|---------|
| 1 | Pairwise accuracy vs heuristic | ≥ 70% |
| 2 | Zero-shot delta (fine-tuned - base) | ≥ +5pp |
| 3 | Hard negative discrimination | ≥ 55% |
| 4 | Cross-course generalization | ≥ 60% |
| 5 | Adversarial trap pairs | ≥ 75% |
| 6 | Spearman ρ vs human ranking | ≥ 0.65 |
| 7 | GPT-judged preference | ≥ 60% |

**Pass ≥ 5/7** = production-ready. See `research/BENCHMARK.md` for full spec.

---

## Hardware

**Primary**: Spark DGX GB10 (`/srv/spark-maker/`)
- GB10 Grace-Blackwell Superchip, 128GB UMA
- Training stack: unsloth + trl + peft + LLaMA-Factory
- `forge` CLI for model loading/slot management

**Alternative**: Brev (isolated, $1-2/hr)

See `research/SPARK_FEASIBILITY.md` for full memory analysis and run commands.

---

## Results

```
rerank_sft.jsonl:     1912 SFTTrainer examples, 797KB
rerank_clean.jsonl:   1912 pairs, balanced A=956/B=956
Pair types:           standard + hard_negative (diff < 3.0)
```

Pipeline validated locally. Run on spark-maker to produce trained adapter.
