# Gemma 2B Reranker — Collaborative Dataset Tools

## Official Tools Used

| Tool | Purpose | Link |
|------|---------|------|
| **Argilla** | Human preference annotation platform (now part of HF) | https://argilla.io |
| **HuggingFace alignment-handbook** | Official HF recipes for DPO/RLHF fine-tuning | https://github.com/huggingface/alignment-handbook |
| **HuggingFace datasets** | Dataset loading, processing, deduplication | https://huggingface.co/docs/datasets |
| **Gemma PEFT** | Official HF blog on Gemma LoRA fine-tuning | https://huggingface.co/blog/gemma-peft |
| **Unsloth** | 2.4x faster fine-tuning (optional) | https://github.com/unslothai/unsloth |

---

## Tool 1: Argilla (Collaborative Annotation)

**What it does**: Web-based UI for human annotators to label pairwise preferences. Each annotator sees a pair of Canvas items and answers "Which is more urgent and why?"

**Setup**:
```bash
pip install argilla
# Start local Argilla instance
argilla server start

# Or use HuggingFace Spaces (zero infra):
# https://argilla.io/spaces
```

**Recommended annotation schema**:
```python
import argilla as rg

# Define the dataset schema for pairwise ranking
dataset = rg.DatasetForTextClassification(
    guidelines="For each pair of Canvas items, select which is more urgent to work on.",
    fields=[
        rg.TextField(name="query"),
        rg.TextField(name="item_a"),
        rg.TextField(name="item_b"),
    ],
    questions=[
        rg.LabelQuestion(
            name="preference",
            labels=["item_a", "item_b"],
            description="Which item is more urgent right now?"
        ),
        rg.MultiLabelQuestion(
            name="reason",
            labels=["time", "points", "grade_impact", "type", "status"],
            description="Why is that item more urgent?"
        ),
    ],
)
```

**Canvas Reranker annotation workflow**:
1. Each teammate runs `collect_rerank_dataset.py generate` locally → gets their `*.jsonl`
2. Merge all teammates' data: `collect_rerank_dataset.py merge`
3. Upload to Argilla for human annotation of ambiguous pairs
4. Export annotated pairs → add to training set

**For this project**: Argilla is overkill for the initial fine-tune. Use it when:
- You have 10+ teammates annotating
- You need to resolve hard negatives (pairs where urgency difference < 3.0)
- You want to collect qualitative "why" explanations

---

## Tool 2: HuggingFace alignment-handbook (Training Recipes)

**What it does**: Official HF's cookbook of robust training recipes for aligning LLMs with human preferences. Includes SFT, DPO, ORPO, KTO.

**Key recipes relevant to this project**:
- `recipes/zephyr-7b-beta/` — DPO on Zephyr-7B (pairwise preference optimization)
- `recipes/constitutional-ai/` — CAI for Gemma models
- `recipes/pref_align_scan/` — Comparison of DPO vs KTO vs IPO

**For Gemma 2B + Canvas reranker**: Use **DPO** (Direct Preference Optimization) since we have pairwise preference labels. DPO is simpler than PPO-based RLHF and works well with ~1000 pairs.

**Relevant alignment-handbook scripts**:
```bash
git clone https://github.com/huggingface/alignment-handbook
cd alignment-handbook

# DPO training recipe
python scripts/dpo_tainer.py \
    --dataset_path data/collab/rerank_clean.jsonl \
    --model_name google/gemma-2b-it \
    --output_dir outputs/gemma2b-reranker-dpo
```

**Important note**: The alignment-handbook uses a specific preference format:
```json
{
  "prompt": "[Query]: What's due today?\nItem A: ...\nItem B: ...",
  "chosen": "Item A is more urgent.\nReason: ...",
  "rejected": "Item B is more urgent.\nReason: ..."
}
```

**Our format maps to this as**:
- `item_a.serialied` + `reason` → `chosen` or `rejected` (depending on preference=1 or 0)
- `query` → part of `prompt`

---

## Tool 3: HuggingFace datasets (Data Processing)

**What it does**: Efficient loading, streaming, and processing of large datasets. Apache Arrow-backed with zero-copy reads.

**Key functions for this project**:
```python
from datasets import load_dataset, DatasetDict

# Load pairwise pairs
ds = load_dataset("json", data_files="data/collab/rerank_clean.jsonl")["train"]

# Train/test split
ds_split = ds.train_test_split(test_size=0.1, seed=42)

# Map to SFTTrainer format
def format_pair(example):
    pref = "A" if example["preference"] == 1 else "B"
    return {
        "text": (
            f"[Query]: {example['query']}\n"
            f"Item A: {example['item_a']['serialized']}\n"
            f"Item B: {example['item_b']['serialized']}\n"
            f"Which is more urgent? Item {pref} is more urgent.\n"
            f"Reason: {example['reason']}<eos>"
        )
    }

ds_formatted = ds_split.map(format_pair, remove_columns=ds_split["train"].column_names)

# Push to HF Hub for sharing
ds_formatted.push_to_hub("your-username/canvas-reranker-pairs")
```

---

## Tool 4: Unsloth (Optional Acceleration)

**What it does**: 2.4x faster fine-tuning, 58% less VRAM usage via custom Triton kernels and gradient checkpointing optimizations.

**Installation**:
```bash
pip install unsloth
```

**Usage** (replaces standard PEFT training):
```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="google/gemma-2b-it",
    max_seq_length=256,
    dtype=None,       # Auto-detect (BF16, FP16, or 4-bit)
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=8,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                   "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0.05,
)

# Standard training loop from here
```

**⚠️ Unsloth constraints**:
- Pins specific versions of torch, triton, xformers
- Best used in a dedicated venv or container (not mixed with other packages)
- Build on Brev instance directly (not inside Docker unless Docker has GPU support)

---

## Collaborative Data Collection Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  Each teammate runs locally (their own Canvas API token)   │
│  python3 collect_rerank_dataset.py generate \               │
│      --output data/collab/{handle}.jsonl \                 │
│      --handle {github_handle}                               │
└─────────────────────┬───────────────────────────────────────┘
                      │ (one JSONL per teammate)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Merge all data                                             │
│  python3 collect_rerank_dataset.py merge \                   │
│      data/collab/*.jsonl \                                 │
│      --output data/collab/rerank_merged.jsonl              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Clean + deduplicate                                       │
│  python3 collect_rerank_dataset.py clean \                 │
│      --input data/collab/rerank_merged.jsonl \            │
│      --output data/collab/rerank_clean.jsonl               │
└─────────────────────┬───────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌──────────────────┐    ┌──────────────────────────────────┐
│ Hard negatives   │    │  Argilla (optional)              │
│ flagged for      │    │  Send ambiguous pairs to        │
│ human review     │    │  teammates for annotation       │
└──────────────────┘    └──────────────┬───────────────────┘
                                        │ (annotated pairs)
                                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Export to SFTTrainer format                               │
│  python3 collect_rerank_dataset.py export-sft \           │
│      --input data/collab/rerank_clean.jsonl \            │
│      --output data/collab/rerank_sft.jsonl                │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Fine-tune Gemma 2B on Brev (L4 / A6000)                  │
│  python3 scripts/train_gemma2b.py \                       │
│      --data data/collab/rerank_sft.jsonl \               │
│      --output outputs/gemma2b-reranker                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Dataset Size & Quality Guidance

| Stage | Pairs Needed | Source |
|-------|-------------|--------|
| Proof-of-concept | ~500 | Klein's data (current) |
| Good quality | ~2,000 | Klein + 2-3 teammates |
| High quality | ~5,000-10,000 | All teammates + Argilla annotation |

**Pair balance target**: 50/50 ± 10% (preference 1 vs 0)
**Hard negative ratio**: ~5-10% of pairs should be hard negatives (urgency diff < 3.0)
**Query diversity**: Use all 17 query templates, not just "what's most urgent"

---

## Data Format — SFTTrainer (Final)

```json
{
  "text": "[Query]: What's the most urgent?\nItem A: [EXAM] Midterm 1 — CS3724 — Tomorrow — 100pts — OPEN\nItem B: [DISC] Discussion 3 — HD3114 — 3d — 5pts — OPEN\nWhich is more urgent? Item A is more urgent.\nReason: Item A is due sooner and is a higher-stakes item type (exam vs discussion).<eos>",
  "id": "kleinpanic-001",
  "pair_type": "standard",
  "source_user": "kleinpanic"
}
```
