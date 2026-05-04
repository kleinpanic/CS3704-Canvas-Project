# Contributing Your Canvas Data

**All you need:** your VT Canvas API token. No other accounts, API keys, or setup required.

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

Replace `yourpid` with your VT PID or any handle. This pulls your courses, assignments, and todo list from Canvas, anonymizes all personal info, and writes a `.jsonl` file to `data/trajectories/collab/yourpid.jsonl`.

**4. Submit your file**

- **Option A — PR:** Add your `data/trajectories/collab/yourpid.jsonl` and open a PR.
- **Option B — Email:** Send the file to rodie105@gmail.com with subject `[CS3704] data - yourpid`.

Klein downloads all contributions and handles the rest.

---

## What gets anonymized

| Original | Replaced with |
|---|---|
| Course names / codes | `COURSE1`, `COURSE2`, … |
| Canvas numeric IDs | deterministic hash |
| Assignment names | kept but IDs replaced |

Your Canvas token is **never** written to the output file.

---

## Troubleshooting

**`CANVAS_TOKEN is not set`** — run `export CANVAS_TOKEN=...` first.

**`401 Unauthorized`** — token expired or copied wrong. Regenerate it in Canvas Settings.

**Empty output** — Canvas returned no active courses. Make sure your token is for an account with current enrollments.
