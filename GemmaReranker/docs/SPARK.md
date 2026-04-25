# Spark Execution Guide

**Approach:** Everything lives in the GitHub repo. Spark clones once, pulls for updates. No rsync, no manual file copying.

---

## One-Time Spark Setup

```bash
# 1. Clone the repo (already done on Spark at /srv/spark-maker/canvas-reranker)
cd /srv/spark-maker/canvas-reranker

# 2. Pull latest (do this before every run)
git pull origin main

# 3. Verify environment
python3 -c 'import os; print("HF_TOKEN:", "OK" if os.environ.get("HF_TOKEN") else "MISSING")'
# Should print: HF_TOKEN: OK

# 4. Verify pipeline scripts
python3 GemmaReranker/scripts/run_pipeline.py --help | head -5
```

## Existing Data on Spark

728 training pairs already exist in the cloned repo at `GemmaReranker/data/rerank_train.jsonl`.
Sample files are also present for reference.

**Need more data?** Teammates contribute via the workflow in Dataset Guide.

---

## Running Path B (standard workflow)

```bash
cd /srv/spark-maker/canvas-reranker

# Always pull latest first
git pull origin main

# Run Path B — will use GemmaSuper as teacher via vLLM
python3 GemmaReranker/scripts/run_pipeline.py \
  --path b \
  --data GemmaReranker/data/rerank_train.jsonl \
  --output /srv/spark-maker/output/pipeline9 \
  --teacher-endpoint http://localhost:8000/v1
```

---

## Starting / Stopping Slots on Spark

The existing Spark infrastructure (slot0, manager, proxy) should already be running. For Path B you need the GemmaSuper slot:

```bash
# Check what's running
forge list

# Start GemmaSuper teacher slot
forge load nvidia/Gemma-4-31B-IT-NVFP4  # loads into slot0

# When done — unload to free GPU memory
forge unload nvidia/Gemma-4-31B-IT-NVFP4
```

> **Note:** `forge` is the only-authorized interface. Do not use `docker run` directly for slot management.

---

## Updating the Repo on Spark

```bash
cd /srv/spark-maker/canvas-reranker
git pull origin main
```

No other sync step needed. All scripts, configs, and data paths in `GemmaReranker/` use relative paths from the project root.

---

## Dataset Contribution (on your machine)

```bash
cd ~/codeWS/Python/CS3704-Canvas-Project/GemmaReranker

# Generate your data (stays private)
cp configs/teammate.env.example .env
# Edit .env: CANVAS_TOKEN, HF_TOKEN, YOUR_HANDLE
python3 scripts/generate_rerank_data.py \
  --token $CANVAS_TOKEN \
  --handle $YOUR_HANDLE \
  --output data/collab/${YOUR_HANDLE}_anon.jsonl

# Commit and push
git checkout -b data/$YOUR_HANDLE
git add data/collab/${YOUR_HANDLE}_anon.jsonl
git commit -m "data: add anonymized dataset from ${YOUR_HANDLE}"
git push origin data/$YOUR_HANDLE
gh pr create --title "Dataset: ${YOUR_HANDLE} contribution"
```

After merging, pull on Spark:
```bash
cd /srv/spark-maker/canvas-reranker
git pull origin main
```
