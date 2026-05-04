# Contributing Trajectory Data

This guide is for CS3704 teammates who want to add their Canvas interaction data to the v2 training dataset. You do **not** need to understand the ML pipeline — just run a script and share the output.

---

## What this does

`scripts/collect_trajectories.py` calls a teacher LLM with your Canvas data attached as context, records how it reasons through calendar and assignment questions, and saves those reasoning traces as anonymized JSONL. Your real name, course IDs, and assignment names never appear in the output — they're hashed or replaced with placeholders before write.

---

## Quick start (5 minutes)

### Step 1 — Get your Canvas API token

1. Log into [canvas.vt.edu](https://canvas.vt.edu)
2. Click your profile picture → **Account** → **Settings**
3. Scroll to **Approved Integrations** → **+ New Access Token**
4. Give it a name (e.g. `cs3704-data`), no expiry needed, click **Generate Token**
5. Copy the token — you'll only see it once

### Step 2 — Clone the repo and install

```bash
git clone https://github.com/kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project
pip install -e .
```

### Step 3 — Run the collector

Replace `yourhandle` with your PID or GitHub username (used only for attribution, never stored alongside your data).

**Option A — Using your own OpenAI key** (easiest, costs ~$0.02 per run with gpt-4o-mini):

```bash
export CANVAS_TOKEN=<your Canvas token from Step 1>
export CANVAS_BASE_URL=https://canvas.vt.edu
export TEACHER_ENDPOINT=https://api.openai.com/v1
export OPENAI_API_KEY=<your OpenAI key>

python3 scripts/collect_trajectories.py \
    --contributor yourhandle \
    --output data/trajectories/collab/yourhandle_trajectories.jsonl \
    --model gpt-4o-mini \
    --max-trajectories 20
```

**Option B — On the VT campus network or VPN** (uses the lab's Spark, no API key needed):

```bash
export CANVAS_TOKEN=<your Canvas token>
export CANVAS_BASE_URL=https://canvas.vt.edu

python3 scripts/collect_trajectories.py \
    --contributor yourhandle \
    --output data/trajectories/collab/yourhandle_trajectories.jsonl \
    --max-trajectories 20
```

### Step 4 — Submit your data

**Path A — GitHub PR** (preferred if you know git):

1. Fork the repo, add your `data/trajectories/collab/yourhandle_trajectories.jsonl`, open a PR to `main`
2. You don't need signed commits for data-only PRs — just push and open the PR

**Path B — Email** (if you don't want to deal with GitHub):

Email `rodie105@gmail.com` with subject `[CS3704] trajectory data - yourhandle` and attach your `.jsonl` file. Klein will add it manually with your contributor ID.

---

## What gets anonymized

The script runs `anonymize_record()` before writing anything:

| Original | Replaced with |
|---|---|
| Course names/codes | `COURSE1`, `COURSE2`, … |
| Assignment titles | deterministic hash |
| Your name in Canvas | deterministic hash |
| Dates | kept (needed for scheduling queries) |

Your Canvas token is **never** written to the output file.

---

## Troubleshooting

**`ModuleNotFoundError: canvas_tui`** — run `pip install -e .` from the repo root first.

**`ConnectionRefusedError` on spark.local** — you're off-campus without VPN. Use Option A (OpenAI key) or email the request to Klein.

**`401 Unauthorized` from Canvas** — your token expired or was copied wrong. Regenerate it in Canvas Settings.

**Script runs but output file is empty** — Canvas returned no courses for the current term. Check that your token points to an active enrollment.

---

## Requirements

- Python 3.11+
- `requests` (installed by `pip install -e .`)
- A VT Canvas account with active courses
- Either: OpenAI API key **or** access to `spark.local:18080` (campus network / VPN)
