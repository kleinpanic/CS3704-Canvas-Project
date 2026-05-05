# Canvas Calendar Agent — Training Pipeline Walkthrough

End-to-end recipe for producing the v3.0 Canvas Calendar Agent: from raw Canvas LMS contributions to released SFT + DPO models, with the agentic harness in `kleinpanic/CS3704-Canvas-Project`. Hardware: NVIDIA DGX Spark (Grace-Blackwell GB10 SoC, 122 GiB unified memory, SM121).

This document supplements `.planning/ROADMAP.md` and per-phase plans by giving the **operational recipe** an outside reader can follow. References to academic foundations (DPO, KTO, etc.) and to the artifacts and scripts that implement each step.

---

## 1. Architecture in one paragraph

A 2.7B-parameter Gemma-4-E2B-IT base is fine-tuned with **Supervised Fine-Tuning** on Canvas-session trajectories that already contain native Gemma-4 tool-call markers, then aligned with **Direct Preference Optimization** (Rafailov et al., 2023) on 1,071 prompt/chosen/rejected triples labeled at temperature 0 by a Gemma-4-31B-IT-NVFP4 teacher running on slot 0 via vLLM. The resulting checkpoint is consumed by `canvas_sdk.CanvasAgent`, which loops `Gemma4Backend → tool_parser → REGISTRY.dispatch → format_tool_result → Gemma4Backend` until the model emits a final answer with no tool call.

---

## 2. Stack and tooling

| Layer | Stack | Notes |
|---|---|---|
| Runtime | DGX Spark (GB10 SoC, 122 GiB UMA) | Single-host, no distributed training |
| Inference (teacher) | vLLM 0.18 + NVFP4 modelopt quant | `vllm/vllm-openai:gemma4-cu130` image |
| Forge router | spark-ai-v2 stack | OpenAI-compatible at `:18080`, handles auth, slot management |
| Training | TRL 1.1 + Transformers 4.47+ + PyTorch 2.10 (NGC 25.11-py3) | Container-based, `docker-compose.training.yaml` |
| Data CLI | `canvas-data` (this repo) | `merge / generate-pairs / label / audit / split-for-release / gen-kto-large / gen-benchmark-large` |
| Train CLI | `canvas-train` (this repo) | `--method {sft, lora, qlora, dpo, ipo, apo-zero, sppo, nca, kto, all}` |
| Anon | `piiranha` (CPU-only) + regex pre-pass | Spacy NER + custom CRN patterns |
| Release | `canvas-release` | GGUF Q2_K..Q8_0 (6 quants × 9 methods) |
| Agentic harness | `canvas_sdk.CanvasAgent` (Canvas-Project repo) | OpenAI-compatible wrapper + tool dispatcher |

---

## 3. Data pipeline

### 3.1 Collection — multi-contributor

Each contributor runs the Canvas TUI's `share_my_canvas.py` extractor, which produces a JSONL snapshot of their courses, assignments, modules, and trajectory recordings. Examples in this dataset:
- `Williammm23.jsonl` (William; 34 courses, 909 assignments)
- `kleinpanic.jsonl`, `Jada-001.jsonl`, etc.

These land in `data/collab/*.jsonl`.

### 3.2 Anonymization — two-pass (CRN + PII)

**Pass 1 — CRN:** `canvas-data merge --inputs data/collab/*.jsonl --out data/merged.jsonl`

`src/dataset/pipeline.py:detect_crn` matches `\b[A-Z]{2,5}_\d{4}_\d+_\d{6}\b` (Virginia Tech CRN form `CS_3704_21936_202601`). `anonymize_crn` builds a stable registry mapping each raw CRN → `@COURSEn`. The merge step also dedups assignments by normalized `(title, course)` key.

**Pass 2 — PII (PERSON, LOC, FAC, emails, phones):** `piiranha` (CPU-only).

The Docker container at `src/docker/Dockerfile.anon-piiranha` runs en_core_web_sm + custom regex on `content`/`text`/`final_answer` fields:

```bash
# CRITICAL: NO --gpus all  (causes OOM with vLLM running)
docker run --rm \
  -i --memory=6g --memory-swap=6g \
  -v $PWD/data:/data \
  pii-anon < data/sft_trajectory_v7_train.jsonl > data/sft_trajectory_v7_train_clean.jsonl
```

Email and phone regex must run as a third pass (piiranha defaults miss `asenger@vt.edu`, `540-231-3788`):

```python
text = re.sub(r"[a-zA-Z0-9._%+-]+@vt\.edu", "@PROF_EMAIL", text)
text = re.sub(r"\b(540|703|804)[-.\s]\d{3}[-.\s]\d{4}\b", "@PHONE", text)
```

Audit gate: `canvas-data audit --train data/train.jsonl --test data/test.jsonl` exits non-zero on any unmasked CRN. CI enforces this.

### 3.3 Trajectory SFT data

`canvas-data trajectory --sessions data/sessions/*.jsonl --out data/sft_trajectory_v7_train.jsonl`

Each row is `{"messages": [...]}` where assistant turns include native Gemma-4 tool-call delimiters: `<|tool_call>call:tool.name{arg:value}<tool_call|>`. The format is a custom variant — NOT JSON. See `src/finetune/utils/tool_parser.py:_TOOL_CALL_RE` for the canonical parser.

181 trajectory rows (post-anon), 46 held out for test.

### 3.4 Preference pair generation + 3-vote labeling

`canvas-data generate-pairs --corpus data/merged.jsonl --out data/pairs.jsonl --max-pairs 2500`

Pairs are sampled from `itertools.combinations` then labeled by `canvas-data label` which sends each `{prompt, item_a, item_b}` through the Gemma-4-31B-IT-NVFP4 teacher at temperature 0, three times. A pair is kept iff all three votes agree (majority 3/3); otherwise discarded. This yields the v7 corpus of 1,842/3,000 pairs labeled, 1,071 in `data/v7/preference_train.jsonl` after dedup + split.

```bash
canvas-data label data/preference_train_v7.jsonl \
  --out data/preference_train_v7_labeled.jsonl \
  --endpoint http://localhost:18080/v1/chat/completions \
  --model gemma4 --workers 2  # 2 to avoid vLLM 504 timeout
```

The teacher is enforced to be Gemma-4 by `_validate_teacher()` (commit 76eb8bf) — `--model gemma4` MUST resolve to `nvidia/Gemma-4-31B-IT-NVFP4` via the forge router.

### 3.5 Split for release

`canvas-data split-for-release --out-dir data/v7 --pref data/preference_train_v7_labeled.jsonl --kto data/kto_train_v7.jsonl --sft-train data/sft_trajectory_v7_train_clean.jsonl`

Produces:
- `data/v7/trajectory_train.jsonl` (181 rows) → SFT
- `data/v7/preference_train.jsonl` (1,071 rows, item-disjoint from test) → DPO family
- `data/v7/kto_train.jsonl` (146 rows) → KTO
- `data/v7/{trajectory,preference,kto}_test.jsonl` → held-out eval

---

## 4. SFT — supervised fine-tuning

**Goal:** Teach Gemma-4-E2B the Canvas-agent system prompt, tool-call delimiter format, and the kind of structured plan we want it to emit (Cepeda-spaced study blocks, exam brackets, rescheduling, etc.).

**Math:** Standard cross-entropy on the assistant turns only. TRL 1.1 enforces this via the `assistant_only_loss=True` flag in `SFTConfig`, which requires the chat template to wrap model turns in `{% generation %}...{% endgeneration %}` markers. Our `_patch_gemma4_chat_template()` in `src/finetune/main.py:140` injects those markers into the upstream Gemma-4 template.

**Hyperparameters** (from `src/finetune/main.py:_run_sft`):

| Field | Value |
|---|---|
| Base model | `google/gemma-4-E2B-it` |
| Precision | bf16 throughout |
| Epochs | 1 |
| Per-device batch size | 1 |
| Gradient accumulation | 8 (effective batch = 8) |
| Learning rate | 2e-5 |
| Optimizer | `paged_adamw_8bit` |
| Max seq length | 4096 |
| Output | `checkpoints/v7-sft/model.safetensors` (~10.2 GB) |

**Run:**
```bash
CANVAS_TRAIN_METHOD=sft docker compose \
  -f docker-compose.training.yaml \
  -p cs3704-sft \
  run --rm --build --entrypoint "" \
  train canvas-train --method sft
```

Wall time: ~10–15 min on GB10. Evaluation: `canvas-data audit --pref data/v7/preference_test.jsonl` plus visual inspection that 3 sample trajectories round-trip cleanly through `tool_parser`.

---

## 5. DPO — Direct Preference Optimization

### 5.1 Background — what DPO is

**Primary reference:** Rafailov, Sharma, Mitchell, Ermon, Manning, Finn. *Direct Preference Optimization: Your Language Model is Secretly a Reward Model*. NeurIPS 2023 (Outstanding Main Track Runner-Up). **arXiv:2305.18290** [cs.LG], 29 May 2023, last revised 13 Dec 2023 (v3). https://arxiv.org/abs/2305.18290

#### What problem the paper solves

Prior to DPO, aligning an LM with human preferences required a 3-stage RLHF pipeline (Christiano et al. 2017; Ziegler et al. 2019; Stiennon et al. 2020; Ouyang et al. 2022): (1) supervised fine-tuning on demonstrations, (2) train a separate reward model on preference data, (3) PPO-optimize the policy against the reward model with a KL constraint to the SFT model. This is operationally complex (rollouts, KL regularization, instability) and requires loading two extra networks during RL.

DPO observes that under the Bradley-Terry preference model and the standard RLHF objective:

```
max_π  E_x~D, y~π(·|x) [r_φ(x, y)] − β · D_KL[π(·|x) ‖ π_ref(·|x)]
```

the closed-form optimum is

```
π*(y|x) = (1/Z(x)) · π_ref(y|x) · exp((1/β) r(x,y))    (Eq. 4)
```

so any reward function can be re-expressed in terms of its optimal policy and the reference: `r(x,y) = β log π(y|x)/π_ref(y|x) + β log Z(x)`. Substituting this into the Bradley-Terry preference probability `P(y_w ≻ y_l | x) = σ(r(x, y_w) − r(x, y_l))`, the partition function `Z(x)` cancels and the preference probability depends only on the policy's log-ratios.

This yields the DPO loss (Eq. 7 in the paper):

```
L_DPO(π_θ; π_ref) = −E_(x,y_w,y_l)~D [
    log σ( β · log π_θ(y_w|x)/π_ref(y_w|x)
         − β · log π_θ(y_l|x)/π_ref(y_l|x) )
]
```

Where:
- `x` is the prompt
- `y_w` is the *preferred* (chosen) response, `y_l` is the rejected response
- `π_θ` is the policy being trained (initialized from SFT)
- `π_ref` is the reference policy (frozen, identical to π_θ at init)
- `β ∈ (0, ∞)` controls deviation from π_ref. Higher β = stay closer to SFT
- `σ` is the logistic function

Equivalently, define the implicit reward `r̂(x,y) = β · log π_θ(y|x) / π_ref(y|x)`; the loss is then binary cross-entropy on the margin `r̂(x, y_w) − r̂(x, y_l)`. The gradient of L_DPO is:

```
∇_θ L_DPO = −β · E_(x,y_w,y_l)~D [
    σ( r̂(x, y_l) − r̂(x, y_w) ) · ( ∇_θ log π_θ(y_w|x) − ∇_θ log π_θ(y_l|x) )
]
```

The first factor `σ(...)` is high when the policy ranks pairs **wrong** relative to π_ref, automatically up-weighting hard examples (Section 4 of the paper).

#### Why it works in practice

The paper's experiments (controlled sentiment generation, summarization on Reddit TL;DR, Anthropic Helpful-Harmless dialogue) show DPO matches or beats PPO-RLHF with **no reward model training, no rollout sampling, no value head, and no KL penalty hyperparameter**. β subsumes the KL coefficient. Stability: DPO loss is convex-ish (binary cross-entropy on a logit), unlike PPO which has the entropy regularizer + clipping + advantage normalization tricks.

#### Practical recipe (Section 6.1 of the paper)

1. Start from a strong SFT model (their `π_SFT`).
2. Use the SFT model as both the initial policy and the reference. Snapshot `π_ref` at training start; do not update.
3. Sweep β ∈ {0.01, 0.1, 0.3, 0.5, 1.0}; β = 0.1 was the sweet spot for HH/summarization, β = 0.5 for IMDB sentiment.
4. Train for 1 epoch over the preference dataset (matches RLHF rollout budget).
5. Learning rate ~1e-6 to 5e-6 with linear warmup; this project uses 5e-6.
6. Effective batch size 32–64 in their experiments; we use 8 because our dataset is only 1,071 pairs.

The TRL implementation in this project uses `loss_type="sigmoid"` (the original DPO loss); related variants (IPO, APO-zero, SPPO, NCA) just swap the loss function while reusing the same machinery.

### 5.1b Cross-audit: implementation vs. arXiv:2305.18290

This project's DPO config (`src/finetune/main.py:_run_dpo_family`, lines 250–260) was audited against the paper's recommendations on 2026-05-06. Findings:

| Hyperparameter | Paper recommendation | Our value | Verdict |
|---|---|---|---|
| Loss function | sigmoid (Eq. 7) | `loss_type="sigmoid"` | ✓ matches |
| β (temperature on KL implicit) | 0.1 default for HH/summarization (§6.1, Table 4) | `beta=0.1` | ✓ matches |
| Reference policy | SFT model, frozen, identical to π_θ at init (§4) | `ref_model=None` + `precompute_ref_log_probs=True` + `sync_ref_model=False` — TRL snapshots policy at init and freezes | ✓ matches semantically |
| Initial policy | SFT model | Loaded from `checkpoints/v7-sft/` (E2B SFT'd on trajectory data) | ✓ matches |
| Epochs | 1 (§6.1) | `num_train_epochs=1` | ✓ matches |
| Learning rate | 1e-6 to 5e-6 typical | `learning_rate=5e-6` | ✓ within range (high end) |
| Effective batch size | 32–64 (paper), our scale smaller | 1 × 8 grad-accum = 8 | ⚠ smaller than paper but appropriate for 1,071 pairs |
| Precision | FP16 in paper | `bf16=True` (Hopper/Ampere preferred over fp16) | ✓ equivalent or better |
| Optimizer | AdamW (paper) | `paged_adamw_8bit` (memory-efficient AdamW) | ✓ same first-order behavior, lower memory |
| Scheduler | Linear warmup | Default linear with `warmup_ratio` (TRL default 0.1) | ✓ matches |
| KL coefficient | None — β subsumes it (§4) | None | ✓ matches |
| Gradient clipping | 1.0 in paper | TRL default 1.0 | ✓ matches |

**Notable deviations and justifications:**

1. **Reference model representation.** The paper (§4) describes π_ref as a separate network. TRL's `precompute_ref_log_probs=True` + `ref_model=None` is functionally equivalent: the reference log-probs `log π_ref(y|x)` are computed in a single pre-training pass over the dataset using the policy's initial weights, cached, and consumed at training time. This **avoids holding two model copies in memory simultaneously** (critical on a 122 GiB UMA system already running vLLM). The reference is mathematically frozen because it was computed from a fixed snapshot. This is the approach used in modern TRL and matches the paper's mathematical specification.

2. **Effective batch size of 8** vs. 32–64 in the paper. Our dataset is 1,071 pairs (the paper's HH dataset has ~170k); a smaller batch improves gradient signal per pair. Larger batches would also have ~134 effective gradient updates per epoch, so the difference is in gradient noise scale, not training budget.

3. **`bf16` over `fp16`.** Equivalent in dynamic range; bfloat16 has the same range as fp32 with reduced precision, avoiding overflow that fp16 sometimes hits during DPO log-prob computation. Not a semantic deviation.

4. **`paged_adamw_8bit`** (bitsandbytes) instead of plain AdamW. The 8-bit quantization affects optimizer state, not gradients or weights. Empirically equivalent first-order convergence with ~75% lower optimizer memory. Required to fit the 2.7B E2B + cached ref logprobs + activations in our memory budget.

**Conclusion:** The implementation faithfully reproduces the DPO loss and training recipe from arXiv:2305.18290 §4–§6.1. No semantic deviations from the paper's specification.

### 5.1c Why DPO over PPO-RLHF for this project

Per the paper's own ablations (Section 6.2, Figure 3): on Anthropic HH-RLHF, DPO with β=0.1 reaches **higher win-rate against the SFT baseline than PPO** with a tuned reward model, while requiring no rollout sampling, no separate reward model, no KL coefficient sweeping, and no value head.

For our scale (E2B = 2.7B params, 1,071 preference pairs, single GB10 SoC), this is decisive:
- PPO would need a reward model: another ~2.7B forward+backward pass during training — doubles GPU memory.
- PPO needs rollout sampling: ~10× longer wall-clock per epoch.
- PPO requires KL coefficient tuning: each value of β needs a separate full training run.
- DPO finishes in ~10 minutes wall-clock. PPO at this scale typically takes 1–2 hours.

**References cited by the paper that we also build on:**
- Bradley & Terry, *Rank analysis of incomplete block designs*, Biometrika 1952 — preference model.
- Christiano et al., *Deep RL from human preferences*, NeurIPS 2017 — original RLHF.
- Stiennon et al., *Learning to summarize with human feedback*, NeurIPS 2020 — TL;DR dataset.
- Ouyang et al., *Training language models to follow instructions with human feedback*, NeurIPS 2022 — InstructGPT.
- Ziegler et al., *Fine-tuning language models from human preferences*, arXiv:1909.08593, 2019 — early RLHF.

### 5.2 Setup choices for this project

| Choice | Value | Justification |
|---|---|---|
| Reference model | SFT checkpoint (E2B), frozen via `precompute_ref_log_probs=True` + `sync_ref_model=False` | Standard DPO recipe (Rafailov §3). Using the 31B teacher as ref was rejected: stronger ref destabilizes gradients and consumes 25 GiB more UMA. |
| β | 0.1 | TRL default; matches DPO paper Table 4 settings for low-data regimes |
| Loss type | `sigmoid` (Rafailov original) | Versions in `loss_map`: `dpo→sigmoid`, `ipo→ipo`, `apo-zero→apo_zero`, `sppo→sppo_hard`, `nca→nca_pair` |
| Padding side | `left` | DPO loss is on response tokens; left-padding keeps the response contiguous at end |
| Precompute ref logprobs | `True` | One-shot pass over the dataset to cache π_ref(y|x); training then needs only π_θ forward pass per step |
| Optimizer | `paged_adamw_8bit` | 8-bit Adam halves optimizer memory; critical for fitting policy + cached ref logprobs in 122 GiB UMA |

`max_prompt_length` and `max_length` were removed from `DPOConfig` in TRL ≥0.12; truncation is now handled by the tokenizer. This bit us at run time on 2026-05-06 and was patched in `src/finetune/main.py:250`.

### 5.3 Pre-training preparation

DPO trains on `data/v7/preference_train.jsonl` (1,071 rows) starting from `checkpoints/v7-sft/model.safetensors`. Each row has fields `pair_id, prompt, pair_type, item_a_id, item_b_id, chosen, rejected`. The TRL `DPOTrainer` consumes the standard `prompt`/`chosen`/`rejected` schema directly.

### 5.4 Hyperparameters

```python
DPOConfig(
    output_dir="checkpoints/v7-dpo",
    loss_type="sigmoid",
    beta=0.1,
    num_train_epochs=1,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,        # effective batch = 8
    learning_rate=5e-6,                   # an order lower than SFT
    bf16=True,
    logging_steps=10,
    save_strategy="epoch",
    sync_ref_model=False,                 # ref stays frozen at SFT
    seed=42,
    precompute_ref_log_probs=True,        # cache π_ref pass once
    optim="paged_adamw_8bit",
)
```

### 5.5 Run

```bash
CANVAS_TRAIN_METHOD=dpo docker compose \
  -f docker-compose.training.yaml \
  -p cs3704-dpo \
  run --rm --build --entrypoint "" \
  train canvas-train --method dpo
```

Phases observed at run time (E2B, 1071 rows):

| Phase | Duration | What it does |
|---|---|---|
| Image build (cached) | ~10 s | Editable install of project + responses |
| Container start | ~5 s | NGC pytorch:25.11 base spins up |
| Weight load | ~1.5 s | 1951 safetensor shards from `checkpoints/v7-sft/` |
| Tokenize dataset | ~2 s | 1071 rows |
| **Compute reference log probs** | ~4 min 15 s | One forward pass per row at 4 it/s (the bottleneck — single GPU, batch 1) |
| **Train (134 effective steps)** | ~5–6 min | grad-accum 8 over 1071 examples, bf16 |
| Save checkpoint | ~5 s | `checkpoints/v7-dpo/model.safetensors` |

Total wall: **~10 min**. Loss should drop from ~0.69 (random preference accuracy) to ~0.4–0.5.

---

## 6. KTO — Kahneman-Tversky Optimization (alternative path)

**Reference:** Ethayarajh et al. *KTO: Model Alignment as Prospect-Theoretic Optimization*. ICML 2024. arXiv:2402.01306.

KTO is included for diversity but DPO is the headline result for v3.0. KTO trains on **scalar desirability** rather than paired preferences (`{x, y, label∈{desirable, undesirable}}`). Useful when paired preferences are unavailable. We use 146 rows (122 desirable, 24 undesirable) generated by `canvas-data gen-kto-large --per-tool 20`.

The TRL `KTOTrainer` uses `ref_model=None` because KTO's per-example loss is not pairwise — TRL handles the implicit reference internally via running statistics. Hyperparameters mirror DPO except `loss_type="kto"` and `desirable_weight=1.0, undesirable_weight=1.0`.

---

## 7. Evaluation

`canvas-data audit --train data/v7/trajectory_train.jsonl --test data/v7/trajectory_test.jsonl` runs the static checks (anon coverage, transitivity, item-disjoint train/test). Beyond that, the human evaluation suite in `tests/test_realistic_use.py` exercises 6 calendar scenarios end-to-end through the agent harness — semester planning, Cepeda spacing, multi-exam scheduling, illness rescheduling, etc. Each scenario asserts that the model emits ≥1 valid tool call sequence and ends with a non-empty final answer.

`canvas-train --method dpo` writes `checkpoints/v7-dpo/trainer_state.json` with the loss curve and gradient norms. A successful run shows `train_loss` monotonically decreasing across the 134 steps.

---

## 8. Agentic harness — `canvas_sdk.CanvasAgent`

Lives in the Canvas-Project repo (`kleinpanic/CS3704-Canvas-Project`, branch `main`). The flow:

```
   User text
     │
     ▼
 CanvasAgent.run()
     │   build messages with system prompt + 18 tool schemas
     ▼
 Gemma4Backend.chat()  ──HTTP──▶  vLLM @ :18080
     │  ◀── raw text including <|tool_call>...<tool_call|>
     ▼
 tool_parser.parse_tool_calls()
     │
     ▼
 agent_tools.dispatch(name, args)  ──▶ Canvas API / Calendar / Study
     │  ◀── result dict
     ▼
 format_tool_result()  →  inject as <|tool_response> message
     │
     └──▶ loop until no tool calls (max 8 turns) → final answer
```

The harness is published in **PR #98** (merged) plus the formatting fix in **PR #100** (merged). Demo script: `scripts/demo_agent.py`. Documentation: `docs-site/agent-demo.md`. The harness imports nothing from the training repo — it only needs `httpx` and the regex-based `tool_parser` (ported as-is from `src/finetune/utils/tool_parser.py`).

---

## 9. Release artifacts (Phase 18)

GGUF export via `canvas-release` produces 6 quantizations × 9 methods = 54 GGUF files for v7:

- Quants: `Q2_K, Q3_K_M, Q4_K_M, Q5_K_M, Q6_K, Q8_0`
- Methods: `sft, dpo, kto, lora, qlora, apo-zero, nca, ipo, sppo`

Old formats `Q4_0, Q4_K_S, Q5_0, Q5_K_S, F16, BF16` deferred to a future milestone (superseded by K-quants or redundant with raw weights).

Two HuggingFace dataset repos + 9 model repos, each with model card + GGUF assets + Zenodo DOI. All gated by `release_gate.py` which blocks publication until `RELEASE-LOG.md` has every rigor check ticked.

---

## 10. References

- **DPO:** Rafailov et al., *Direct Preference Optimization: Your Language Model is Secretly a Reward Model*, NeurIPS 2023. **arXiv:2305.18290**.
- **IPO:** Azar et al., *A General Theoretical Paradigm to Understand Learning from Human Preferences*, AISTATS 2024. arXiv:2310.12036.
- **KTO:** Ethayarajh et al., *KTO: Model Alignment as Prospect-Theoretic Optimization*, ICML 2024. arXiv:2402.01306.
- **APO-zero:** D'Oosterlinck et al., *Anchored Preference Optimization*, 2024. arXiv:2408.06266.
- **SPPO:** Wu et al., *Self-Play Preference Optimization for Language Model Alignment*, 2024. arXiv:2405.00675.
- **NCA:** Chen et al., *Noise Contrastive Alignment*, 2024. arXiv:2402.05369.
- **TRL:** Hugging Face TRL library, `DPOTrainer`/`SFTTrainer`/`KTOTrainer` implementations. https://github.com/huggingface/trl
- **Gemma-4:** Google DeepMind, *Gemma 4 technical report*, 2026.
- **Cepeda spaced repetition:** Cepeda et al., *Distributed practice in verbal recall tasks: A review and quantitative synthesis*, Psychological Bulletin 2006.

---

## 11. Operational gotchas (learned the hard way)

1. **Forge load takes a model name, not a path.** `forge load nvidia/Gemma-4-31B-IT-NVFP4` works; `forge load /srv/.../GemmaSuper` does not. See `.planning/research/FORGE-CLI-REFERENCE.md`.
2. **`forge ps` is the only truth.** `curl :18080/health` only proves the proxy is up — vLLM may have crashed.
3. **Piiranha CPU-only.** `docker run --memory=6g` (NO `--gpus all`) — combining piiranha GPU with vLLM caused two OOM events on 2026-05-05.
4. **GPU util 0.60 lock.** Both `slot0.env` files set `GPU_MEMORY_UTIL=0.60` to leave headroom for concurrent training.
5. **Docker `CANVAS_TRAIN_METHOD` shell expansion is broken** with `ENTRYPOINT ["canvas-train"]`. Use `--entrypoint ""` and pass `canvas-train --method X` as command-args.
6. **TRL `max_prompt_length` removed** in 0.12+. `DPOConfig` no longer accepts it.
7. **DPO labeling: 2 workers max** with vLLM under contention. 4 workers + concurrent gen-kto-large + bench gives 504 Gateway Timeouts.
8. **3-vote majority is strict.** A single vote failure (None) → discard. This is intentional; the alternative (2/3 majority) admits noisier labels and degraded DPO outcome.
