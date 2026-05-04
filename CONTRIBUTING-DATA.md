# Contributing Your Canvas Data

## What you need

- Your VT Canvas API token
- Python 3.11+
- The repo cloned with `pip install -e .` run from the root

## Steps

**1. Get your Canvas token**

Go to canvas.vt.edu → Account → Settings → Approved Integrations → New Access Token.

**2. Run the collection script**

```bash
export CANVAS_TOKEN=your_token_here
export CANVAS_BASE_URL=https://canvas.vt.edu
export TEACHER_ENDPOINT=https://api.openai.com/v1
export OPENAI_API_KEY=your_openai_key

python3 scripts/collect_trajectories.py \
    --contributor yourpid \
    --output data/trajectories/collab/yourpid.jsonl
```

Replace `yourpid` with your VT PID or any handle. Your name and course info are anonymized before the file is written.

**3. Submit your file**

Option A — open a PR adding `data/trajectories/collab/yourpid.jsonl`.

Option B — email the file to rodie105@gmail.com with subject `[CS3704] data - yourpid`.

That's it. Klein handles the rest.
