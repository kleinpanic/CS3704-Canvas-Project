# GemmaReranker — DPO Training for Canvas Priority Reranker

Self-contained project for training a DPO-based priority reranker for the Canvas Deadline Tracker.

## Quick Links

- [Architecture & Setup Plan](docs/ARCHITECTURE.md) — full system design
- [Execution Guide](docs/SETUP.md) — step-by-step run instructions
- [Dataset Contribution Guide](docs/DATASET.md) — how teammates contribute data

## What's Here

```
GemmaReranker/
├── docker/          # Docker compose files for teacher + student slots + trainer
├── scripts/         # All pipeline scripts (self-contained copies)
├── configs/         # ENV templates for each Docker slot
├── data/            # collab/ (PRIVATE teammate data), train/test JSONL
└── docs/            # Architecture, setup, dataset guides
```

## Current Status

- [ ] Phase 1: Spark sync + Gemma license — DONE (Klein)
- [ ] Phase 2: Teammate data collection — PENDING (need 3+ contributors)
- [ ] Phase 3: Run Pipeline Path B — PENDING
- [ ] Phase 4: Validate benchmark — PENDING

## Key Papers

- [DPO: Direct Preference Optimization](https://arxiv.org/pdf/2305.18290) (Rafailov et al., 2023)
- [Attention Is All You Need](https://arxiv.org/pdf/1706.03762) (Vaswani et al., 2017)
