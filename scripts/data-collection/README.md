# Data Collection

Scripts for contributing Canvas data to the CS3704 v2 training dataset.

## Quick start

**All you need:** a VT Canvas API token. No other accounts or API keys required.

```bash
pip install requests

export CANVAS_TOKEN=your_token_here
python3 scripts/data-collection/share_my_canvas.py --contributor yourpid
```

This pulls your courses, assignments, and todo list from Canvas, anonymizes all personal info (course codes → `COURSE1`, Canvas IDs → hashed stubs), and writes a `.jsonl` file to `data/trajectories/collab/yourpid.jsonl`.

## Submitting your data

- **PR:** Add your `data/trajectories/collab/yourpid.jsonl` and open a pull request.
- **Email:** Send the file to rodie105@gmail.com with subject `[CS3704] data - yourpid`.

See [CONTRIBUTING-DATA.md](../../CONTRIBUTING-DATA.md) for full details.

## Scripts

| File | Purpose |
|---|---|
| `share_my_canvas.py` | Scrape your Canvas data → anonymized JSONL. Run this. |

## What gets anonymized

| Original | Replaced with |
|---|---|
| Course names / codes | `COURSE1`, `COURSE2`, … |
| Canvas numeric IDs | deterministic SHA-based stub |
| Assignment names | kept (titles are generic) |

Your Canvas token is **never** written to any output file.
