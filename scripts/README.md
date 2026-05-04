# Contributing Canvas Data

All you need is your VT Canvas API token. No other accounts, API keys, or setup required.

---

## Steps

**1. Get your Canvas token**

Go to [canvas.vt.edu](https://canvas.vt.edu) → Account → Settings → Approved Integrations → **+ New Access Token**.

**2. Clone the repo**

```bash
git clone https://github.com/kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project
pip install requests
```

**3. Run the script**

```bash
export CANVAS_TOKEN=your_token_here
python3 scripts/share_my_canvas.py --contributor yourpid
```

Replace `yourpid` with your VT PID or GitHub handle. The script pulls your full 4-year Canvas history (all courses, all assignments, submission status), anonymizes everything on your machine, and writes `data/collab/yourpid.jsonl`.

**4. Submit your file**

- **PR:** Add `data/collab/yourpid.jsonl` and open a pull request.
- **Email:** Send to rodie105@gmail.com with subject `[CS3704] data - yourpid`.

That's it.

---

## What gets anonymized

| Original | Replaced with |
|---|---|
| Course codes (e.g. `CS 3704`, `ENGL2204`) | `@COURSE1`, `@COURSE2`, … |
| Canvas numeric IDs (7–9 digit numbers) | deterministic hash (`ID######`) |

Assignment names are kept as-is. Your Canvas token is **never** written to the output file.

---

## For Klein — converting contributions

After receiving files in `data/collab/`, run:

```bash
python3 scripts/convert_canvas_contributions.py \
    --input  data/collab/ \
    --output data/canvas_items_collab.jsonl \
    --dedupe-against data/canvas_items_v4.jsonl
```

This converts the snapshot records to the flat `canvas_items` format the training pipeline uses.
