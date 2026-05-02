# GemmaReranker — Multi-Method Fine-Tuning for Canvas Priority Reranker

Source-of-truth pipeline for training Canvas LMS preference rerankers
on Gemma-4-E2B-IT. Compares 9 fine-tuning methods (SFT, LoRA, QLoRA,
DPO, IPO, APO-zero, SPPO, NCA, KTO) on a single shared corrected base
and a single item-disjoint train/test split.

## 🔗 Published artifacts

| Artifact | URL |
|----------|-----|
| **HF Collection** (all variants + dataset + paper) | [huggingface.co/collections/kleinpanic93/canvas-reranker-gemma-4-e2b-it-v10-69f5799662d65c8f39be0a94](https://huggingface.co/collections/kleinpanic93/canvas-reranker-gemma-4-e2b-it-v10-69f5799662d65c8f39be0a94) |
| **Primary model repo** (4 GGUF quants + BF16 + paper) | [`kleinpanic93/gemma4-canvas-reranker`](https://huggingface.co/kleinpanic93/gemma4-canvas-reranker) |
| **Method-variant repos** | `kleinpanic93/gemma4-canvas-reranker-{sft,lora,qlora,dpo,ipo,apo-zero,sppo,nca,kto}` |
| **Dataset** | [`kleinpanic93/canvas-preference-2k`](https://huggingface.co/datasets/kleinpanic93/canvas-preference-2k) (1,347 unique pairs) |
| **Paper** | `paper/main.pdf` in primary model repo (Zenodo DOI pending) |

## Quick Links

- [Architecture & Setup Plan](docs/ARCHITECTURE.md) — full system design
- [Execution Guide](docs/SETUP.md) — step-by-step run instructions
- [Dataset Contribution Guide](docs/DATASET.md) — how teammates contribute data

## What's Here

```
GemmaReranker/
├── docker/          # Docker compose files for teacher + student slots + trainer
├── scripts/         # All pipeline scripts (data prep + train + bench + publish)
├── configs/         # ENV templates for each Docker slot
├── data/            # collab/ (PRIVATE teammate data), train/test JSONL
└── docs/            # Architecture, setup, dataset guides
```

### Scripts overview

**Data prep** (canonical training-data generators):
- `generate_rerank_data.py` — main pair generator (multi-dimensional urgency)
- `collect_rerank_dataset.py` — splitter + deduplicator + format_for_dpo
- `generate_teacher_preferences.py` — two-call directed teacher distillation
- `scrub_names.py`, `scrub.py`, `convert_to_pipeline.py` — anonymization + format conversion
- `prep_dataset_release.py` — final dedup + `preference_signal_present` annotation
- `audit_dataset.py` — pre-release PII / schema / hallucination scan

**Training** (one method per script):
- `extract_text_base.py` — recover `gemma4-text-base` from the multimodal Gemma-4 checkpoint
- `train_v4_matrix.py` — 9-method matrix runner (SFT/LoRA/QLoRA/DPO/IPO/APO-zero/SPPO/NCA/KTO)
- `train_dpo.py`, `train_dpo_v3.py` — single-method DPO drivers (legacy + held-out-validation reproducible)

**Validation + bench**:
- `validate_dpo_holdout.py` — held-out logprob-delta + pairwise prediction with Wilson 95% CIs
- `benchmark_quants.py` — multi-quant accuracy + latency on the held-out set
- `bench_v4_methods.py` — apples-to-apples cross-method comparison
- `benchmark.py`, `run_benchmark.py` — Phase 06 single-letter benchmark (legacy, kept for reproducibility)

**Inference + export**:
- `export_gguf.py` — QLoRA merge + GGUF export
- `smoke_test_gguf.py` — quick GGUF sanity check
- `latency_bench.py` — INT-03 latency measurement

**Publishing**:
- `publish_v4_models.py` — push each variant to its own HF repo + add to Collection
- `deposit_zenodo.py` — paper DOI via Zenodo REST API

## Current status

- ✅ Phase 1: Spark sync + Gemma license
- ✅ Phase 2: Single-contributor data collection (1,347 unique pairs; multi-contributor deferred to v2)
- ✅ Phase 3: Pipeline executed (v1 random-init bug + v2 corrected retrain + v3 held-out + v4 multi-method)
- ✅ Phase 4: Held-out benchmark on n=148 item-disjoint pairs
- ✅ Phase 5: Public release on Hugging Face (model + dataset + Collection + paper)

## Key papers

- [Rafailov 2023 — DPO](https://arxiv.org/abs/2305.18290) — canonical preference optimization
- [Azar 2023 — IPO](https://arxiv.org/abs/2310.12036) — fixes DPO overoptimization
- [Pan 2024 — APO](https://arxiv.org/abs/2408.06266) — anchored preference optimization
- [Wu 2024 — SPPO](https://arxiv.org/abs/2405.00675) — self-play preference optimization
- [Chen 2024 — NCA](https://arxiv.org/abs/2402.05369) — noise-contrastive alignment
- [Ethayarajh 2024 — KTO](https://arxiv.org/abs/2402.01306) — Kahneman-Tversky optimization
- [Liu 2024 — Reference Policies in DPO](https://arxiv.org/abs/2407.13709) — reference policy as upper bound
- [Feng 2026 — SFT-DPO Interaction](https://arxiv.org/abs/2603.20100) — concurrent finding at GPT-2 scale
- [Hu 2022 — LoRA](https://arxiv.org/abs/2106.09685), [Dettmers 2023 — QLoRA](https://arxiv.org/abs/2305.14314)
