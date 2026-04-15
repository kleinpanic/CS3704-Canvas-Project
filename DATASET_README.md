# Gemma 2B Reranker — Collaborative Dataset

**Privacy-first dataset collection for training a Canvas priority reranker.**

---

## Quick Start

```bash
# 1. Add your Canvas token to ~/.zshenv
export CANVAS_TOKEN="your_canvas_api_token"
export CANVAS_BASE_URL="https://canvas.vt.edu"  # or your Canvas instance
source ~/.zshenv

# 2. Generate YOUR dataset (stays private on your machine)
python3 scripts/collect_rerank_dataset.py generate \
    --output data/collab/YOUR_HANDLE.jsonl \
    --handle YOUR_HANDLE

# 3. ANONYMIZE before contributing (REQUIRED)
python3 scripts/collect_rerank_dataset.py anonymize \
    --input data/collab/YOUR_HANDLE.jsonl \
    --output data/collab/YOUR_HANDLE_anon.jsonl

# 4. Submit YOUR_HANDLE_anon.jsonl (NOT the raw file)
#    Do NOT commit the raw file — it contains your course codes and item names.
```

---

## Privacy Rules (MUST READ)

### What `--anonymize` does

The `anonymize` command transforms your data to remove identifying information:

| Before | After |
|--------|-------|
| `CS2505` (course code) | `COURSE001` |
| `Intro Computer Organization I` (course name) | **removed** |
| `Homework 4 — Managing a Roster of Names in C` (title) | `Homework` |
| `2026-04-15T23:59:00Z` (absolute due date) | **removed** |
| `kleinpanic` (your handle) | `contributor001` |
| `id: 4872350` (item ID) | new random ID |

**What it keeps**: relative urgency signals (hours until due), point values, assignment types, submission status, and the pairwise preference labels. These are sufficient for training the reranker and do not identify you.

### What NEVER to commit

- ❌ `data/collab/*.jsonl` — raw files with your course codes, item names, and timestamps
- ❌ Files without running `--anonymize` first
- ❌ Real names, email addresses, or student IDs

### What IS safe to commit

- ✅ `data/collab/*_anon.jsonl` — anonymized files with `_anon` suffix
- ✅ `data/rerank_clean.jsonl` — merged + anonymized dataset (after review)
- ✅ Aggregate statistics (number of pairs, preference distribution) without individual data

### Course Map

When you anonymize, a `.course_map.json` file is created alongside the output.
**DO NOT commit this file** — it maps your real course IDs to anonymized codes.

---

## Teammate Contribution Workflow

```bash
# Each teammate does steps 1-3 locally:

# Step 1: Setup (once per machine)
python3 scripts/collect_rerank_dataset.py setup
# → enters token, saves to ~/.zshenv

# Step 2: Generate your private data
python3 scripts/collect_rerank_dataset.py generate \
    --output data/collab/your_handle.jsonl \
    --handle your_handle

# Step 3: Anonymize (before sharing)
python3 scripts/collect_rerank_dataset.py anonymize \
    --input data/collab/your_handle.jsonl \
    --output data/collab/your_handle_anon.jsonl

# Step 4: Submit your_handle_anon.jsonl to the team (via PR or shared drive)
# The anonymized file is safe to share publicly.

# Team lead merges (step 5+):
# Step 5: Merge all teammates' anonymized files
python3 scripts/collect_rerank_dataset.py merge \
    data/collab/*_anon.jsonl \
    --output data/collab/rerank_merged.jsonl

# Step 6: Clean + balance
python3 scripts/collect_rerank_dataset.py clean \
    --input data/collab/rerank_merged.jsonl \
    --output data/collab/rerank_clean.jsonl

# Step 7: Export for Gemma 2B training (SFT)
python3 scripts/collect_rerank_dataset.py export-sft \
    --input data/collab/rerank_clean.jsonl \
    --output data/rerank_sft.jsonl

# Step 7b: Export for Path B DPO distillation (optional)
python3 scripts/collect_rerank_dataset.py export-dpo \
    --input data/collab/rerank_clean.jsonl \
    --output data/rerank_dpo.jsonl

# Step 8: Train (see Gemma2B-Reranker/plans/PLAN.md)
```

---

## Data Format

### Raw pairs (before anonymize)
```json
{
  "id": "a1b2c3d4",
  "query": "What's the most urgent?",
  "item_a": { "id": 4872350, "name": "Homework 4", "course_code": "CS2505", ... },
  "item_b": { "id": 4872399, "name": "Quiz 2", "course_code": "NEUR2464", ... },
  "preference": 1,
  "urgency_a": 62.7, "urgency_b": 44.2,
  "reason": "Item A has higher urgency (A=62.7 B=44.2, diff=18.5)",
  "source_user": "kleinpanic"
}
```

### Anonymized pairs (safe to share)
```json
{
  "id": "e5f6g7h8",
  "query": "What's the most urgent?",
  "item_a": { "type": "assignment", "course_code": "COURSE001", "hours_until_due": 24.0, ... },
  "item_b": { "type": "quiz", "course_code": "COURSE002", "hours_until_due": 48.0, ... },
  "preference": 1,
  "urgency_a": 62.7, "urgency_b": 44.2,
  "reason": "Item A has higher urgency...",
  "source_user": "contributor001",
  "_anon": true
}
```

---

## Anonymization Verification

Before contributing, verify your anonymized file is clean:

```bash
# Should print nothing if clean:
grep -iE "kleinpanic|collin|@vt.edu|@proton.me|cs2505|cs3704|neur2464|hd3114" \
    data/collab/YOUR_HANDLE_anon.jsonl && echo "FOUND PRIVATE DATA — DO NOT COMMIT" || echo "Clean ✓"

# Check no course names remain:
grep -iE "intro computer|neuroscience|human dev|physiology" \
    data/collab/YOUR_HANDLE_anon.jsonl && echo "FOUND COURSE NAMES" || echo "Course names removed ✓"
```

---

## No Token? No Problem

If your teammates don't have Canvas API tokens set up yet, they can:
1. Use the `--courses` flag with specific course IDs they want to include
2. Wait until tokens are set up
3. Submit an anonymized file with only the courses they chose to share

The pipeline works with any number of contributors — even 1 person's data is sufficient to train a working reranker.

---

## Questions?

Open an issue or reach out to the maintainer.
