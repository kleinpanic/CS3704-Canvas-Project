# Trajectory Data

This directory holds v2 calendar-agent training trajectories.

```
data/trajectories/
├── seeds/      # 50 seed JSONL files (canonical examples per bucket)
├── collab/     # Teammate contributions — one JSONL per contributor run
└── README.md
```

## Contributing

Run the collection script to generate your trajectory file:

```bash
export CANVAS_TOKEN=your_canvas_token
export CANVAS_BASE_URL=https://canvas.vt.edu

python3 scripts/collect_trajectories.py \
    --contributor YOUR_HANDLE \
    --output data/trajectories/collab/YOUR_HANDLE_trajectories.jsonl \
    --max-trajectories 20
```

Then open a PR adding your `data/trajectories/collab/YOUR_HANDLE_trajectories.jsonl` file.

## Format

Each JSONL line is one trajectory:
```json
{"user_query": "...", "context": {...}, "trajectory": [...], "teacher_model": "...", "contributor_id": "..."}
```

All PII is anonymized before write (course codes → `COURSE<N>`, names → deterministic hashes).

## Requirements

- `CANVAS_TOKEN` in your environment pointing to your VT Canvas account
- Network access to `spark.local:18080` (or override with `--endpoint`)
- Python 3.11+ with `canvas_sdk` installed (`pip install -e .` from repo root)
