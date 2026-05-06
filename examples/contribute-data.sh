#!/usr/bin/env bash
# contribute-data.sh — collect Canvas data, scrub PII, open a contribution PR
# Run: bash examples/contribute-data.sh
# Docs: docs/contributing-data.md
set -euo pipefail

# --- Require env vars ---
if [[ -z "${CANVAS_BASE_URL:-}" ]]; then
    echo "WARN: CANVAS_BASE_URL is not set." >&2
    echo "  export CANVAS_BASE_URL=\"https://your-institution.instructure.com\"" >&2
    exit 1
fi

if [[ -z "${CANVAS_TOKEN:-}" ]]; then
    echo "WARN: CANVAS_TOKEN is not set." >&2
    echo "  export CANVAS_TOKEN=\"your_token\"" >&2
    echo "  Canvas -> Account -> Settings -> New Access Token" >&2
    exit 1
fi

# --- Confirm we're in the repo root ---
if [[ ! -f "scripts/share_my_canvas.py" ]]; then
    echo "ERROR: Run this script from the repo root (CS3704-Canvas-Project/)." >&2
    exit 1
fi

# --- Install SDK if needed ---
if ! python3 -c "import canvas_sdk" 2>/dev/null; then
    echo "Installing canvas-sdk..."
    python3 -m pip install --quiet canvas-sdk
fi

echo ""
echo "Collecting and scrubbing your Canvas data..."
echo "  This will:"
echo "    1. Pull courses, assignments, and calendar data from your Canvas instance."
echo "    2. Strip PII via the canvas-pii-scrub HuggingFace Space (falls back to local)."
echo "    3. Write the scrubbed output to data/collab/<your_contributor_id>.jsonl"
echo ""
echo "  Your personal data never leaves the scrub step unprocessed."
echo "  See docs/contributing-data.md for the full privacy model."
echo ""

# Run the collection + PII scrub pipeline
python3 scripts/share_my_canvas.py \
    --scrub-via-space \
    --inspect

echo ""
echo "Collection complete."
echo ""
echo "To contribute, open a PR against the 'main' branch:"
echo "  1. Create a branch: git checkout -b contribute/my-data"
echo "  2. Stage the output: git add data/collab/<your_contributor_id>.jsonl"
echo "  3. Commit: git commit -m 'data: add contribution from <your_contributor_id>'"
echo "  4. Push and open a PR on GitHub."
echo ""
echo "Full instructions: docs/contributing-data.md"
