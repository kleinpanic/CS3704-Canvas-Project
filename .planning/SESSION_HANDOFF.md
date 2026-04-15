# Session Handoff — CS3704 Canvas Reranker Pipeline
**Last updated:** 2026-04-15  
**GSD Phase:** Pre-training prep complete. Ready to run.

---

## What This Project Is
CS3704 semester project: a Canvas LMS TUI + a Gemma reranker that priority-sorts Canvas assignments.
The reranker is trained via QLoRA (Path A) and DPO distillation from Gemma 4 teacher (Path B).

**Repo:** `~/codeWS/Python/CS3704-Canvas-Project/`  
**Spark path:** `/srv/spark-maker/gemma2b-reranker/`  
**Spark access:** `ssh spark` — NEVER via web/node interface

---

## Current State (2026-04-15 end of session)

### What works
- CI/CD: all passing on GitHub (ci.yml, coverage, pages, security)
- Dataset: 1,719 train pairs + 193 test pairs at `/srv/spark-maker/gemma2b-reranker/data/`
- Scripts: synced to Spark, all critical bugs fixed
- Training pipeline: `run_pipeline.py` — state machine, resumable via `/tmp/pipeline_state.json`

### Why pipeline7 failed
`google/gemma-2b-it` 403 error — gated model. The HF_TOKEN is set on Spark (`hf_KtWzGBx...`) for `kleinpanic93` which HAS accepted the Gemma license. The fix is now in the code (explicit `token=HF_TOKEN` passed to `from_pretrained`).

**New student model: `google/gemma-3-4b-it`** (Gemini recommended; DGX GB10 has 130GB, easily handles 4B. Gemma 3 has better reasoning than Gemma 2B.)

### What needs to happen to run training
1. `ssh spark`
2. Verify Gemma 3 license accepted: `python3 -c "from huggingface_hub import model_info; print(model_info('google/gemma-3-4b-it').card_data)"` 
3. If gated: accept at https://huggingface.co/google/gemma-3-4b-it (HF account: kleinpanic93)
4. Delete old state: `rm -f /tmp/pipeline_state.json`
5. cd to `/srv/spark-maker/gemma2b-reranker`
6. `tmux new -s pipeline -d`
7. `tmux send-keys 'python3 scripts/run_pipeline.py --data data/rerank_train.jsonl --output /srv/spark-maker/output/pipeline8 --state /tmp/pipeline_state.json' Enter`
   (HF_TOKEN is in spark's zshenv — will be inherited by subprocess automatically)
8. Monitor: `tmux attach -t pipeline`

### Gemma 4 teacher on Spark (for Path B)
- File: `/srv/spark-ai-v2/compose.slot0-gemma4.yaml`
- Image: `nvcr.io/nvidia/vllm:26.02-py3` (official Nvidia NGC)
- Must be loaded BEFORE Path B runs
- Load cmd: `docker compose -f /srv/spark-ai-v2/compose.base.yaml -f /srv/spark-ai-v2/compose.vllm.yaml -f /srv/spark-ai-v2/compose.slot0-gemma4.yaml up -d spark-vllm-slot0`
- Or via forge: `forge load nvidia/Gemma-4-31B-IT-NVFP4 --slot 0`
- Verify endpoint: `curl http://localhost:8000/v1/models`

---

## Bugs Fixed This Session (2026-04-15)

| Bug | File | Fix |
|-----|------|-----|
| Path B path TypeError `"path_b"/"file"` | run_pipeline.py | Fixed to `Path(...) / "path_b" / "file"` |
| DPO label swap (chosen/rejected inverted when B wins) | generate_teacher_preferences.py | Fixed — chosen always gets actual reasoning |
| Uppercase-then-count-lowercase bug (parse_teacher_response) | generate_teacher_preferences.py | Fixed to count only uppercase after `.upper()` |
| QLoRA 4-bit never actually applied (`get_bnb_config` dead code) | train_gemma2b.py | Fixed — now passes `quantization_config=` |
| LoRA rank 64 → too large for small dataset | train_gemma2b.py | Lowered to r=16, alpha=32 |
| warmup_steps=3 → too low | train_gemma2b.py | Raised to 20 |
| Optimizer `paged_adamw_32bit` crashes without bitsandbytes | train_gemma2b.py | Gated on BNB_AVAILABLE |
| No gradient checkpointing | train_gemma2b.py | Added to SFT_ARGS |
| No eval split → no overfitting detection | train_gemma2b.py | 10% eval split, eval every 50 steps |
| pad_token = eos_token (pollutes EOS embedding) | train_gemma2b.py | Add dedicated [PAD] token |
| HF_TOKEN not passed explicitly | train_gemma2b.py | Added explicit `token=HF_TOKEN` |
| BF16 no runtime guard | train_gemma2b.py | Added `is_bf16_supported()` check |
| DPO rejected = stub "Item X is less urgent." | collect_rerank_dataset.py | Now generates plausible-but-wrong alternative reasoning |
| LLaMA-Factory dependency in path_b_tui.py | path_b_tui.py | Replaced with TRL DPOTrainer (already a dep) |
| path_b_tui.py student model = wrong Llama model | path_b_tui.py | Fixed to `google/gemma-3-4b-it` |
| teacher model not passed to preference generation subprocess | path_b_tui.py | Added `--teacher-model` arg passthrough |
| teacher max_tokens=256 → responses truncated | generate_teacher_preferences.py | Raised to 350 |
| sm_100 missing from Dockerfile CUDA arch list (GB10) | reranker/docker/Dockerfile | Added `100` |

---

## Pipeline Architecture

```
Canvas API (Klein's courses)
    ↓
collect_rerank_dataset.py generate → data/collab/kleinpanic.jsonl
    ↓ anonymize
    ↓ merge + clean + split
    ↓
rerank_train.jsonl (1,719 pairs) + rerank_test.jsonl (193 pairs)
    ↓
run_pipeline.py ──────────────────────────────────────────────────
    ├── PATH A-1: SFT export → train_gemma2b.py (QLoRA, standard pairs)
    ├── PATH A-2: SFT export → train_gemma2b.py (QLoRA, hard negatives)
    └── PATH B:  DPO export → generate_teacher_preferences.py (Gemma 4 31B teacher)
                            → path_b_tui.py run_dpo_training (TRL DPOTrainer)
    ↓
benchmark.py (eval all adapters on test set)
    ↓
Best adapter → export_gguf.py → GGUF for inference in TUI
```

---

## Model Selection (Gemini-audited 2026-04-15)
- **Student:** `google/gemma-4-2b-it` (Gemma 4, same generation as the teacher; compact 2B for reranker task)
- **Teacher:** `nvidia/Gemma-4-31B-IT-NVFP4` (loaded on Spark vLLM slot 0 for Path B)
- **QLoRA config:** r=16, alpha=32, all 7 Gemma attention+MLP modules, NF4 4-bit, BF16 compute

---

## GSD Workflow for Next Session

### Resume steps
```bash
# On local machine:
/gsd-resume  # or check ~/.openclaw/workspace-school/memory/

# Check pipeline state:
ssh spark "cat /tmp/pipeline_state.json"

# If pipeline8 running, monitor:
ssh spark "tmux attach -t pipeline"

# If not running, check last error:
ssh spark "tail -50 /srv/spark-maker/output/pipeline8/pipeline.log"
```

### If pipeline8 succeeded
1. Check benchmark results: `ssh spark "cat /srv/spark-maker/output/pipeline8/pipeline_report.json"`
2. Best adapter is in `best_adapter` field
3. Export to GGUF: `python3 scripts/export_gguf.py --adapter output/pipeline8/<best>`
4. Integrate adapter into Canvas TUI (`src/canvas_tui/`)

### If pipeline8 failed
1. Read the log for error
2. Delete state: `ssh spark "rm /tmp/pipeline_state.json"`
3. Common fixes:
   - Gemma 3 gated: accept license at huggingface.co/google/gemma-3-4b-it
   - OOM: Unload other models first via `forge unload 0`
   - Path B teacher missing: load Gemma 4 via forge first

---

## Files That Matter

| File | Purpose |
|------|---------|
| `scripts/run_pipeline.py` | Main orchestrator — start here |
| `scripts/train_gemma2b.py` | QLoRA SFT trainer (google/gemma-3-4b-it) |
| `scripts/generate_teacher_preferences.py` | Calls Gemma 4 teacher via vLLM API |
| `scripts/path_b_tui.py` | DPO training via TRL DPOTrainer |
| `scripts/benchmark.py` | Eval adapters on test set |
| `scripts/collect_rerank_dataset.py` | Dataset generation + DPO/SFT export |
| `reranker/docker/Dockerfile` | Training container (cuda 12.4 + sm_100) |
| `/srv/spark-ai-v2/compose.slot0-gemma4.yaml` | Gemma 4 vLLM slot config (on Spark) |
| `.planning/SESSION_HANDOFF.md` | This file |

---

## Things NOT Done (next session)
- [ ] Accept Gemma 3 license at huggingface.co/google/gemma-3-4b-it
- [ ] Run pipeline8 (first clean run with all fixes)
- [ ] Set up Gemma 4 isolation on Spark (verify compose.slot0-gemma4.yaml env vars)
- [ ] Integrate best adapter into TUI src/canvas_tui/
- [ ] G2: Add direct heuristic-DPO path (train on format_for_dpo without teacher) as ablation
- [ ] G6: Verify training data is anonymized (source_user field has real handle "kleinpanic" currently)
