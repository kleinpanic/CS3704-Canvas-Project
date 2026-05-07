#!/usr/bin/env bash
# quickstart-tui.sh — install canvas-tui and launch the terminal UI
# Run: bash examples/quickstart-tui.sh
# Docs: docs/QUICKSTART.md
set -euo pipefail

# --- Check Python 3.11+ ---
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c 'import sys; print(sys.version_info >= (3, 11))')
        if [[ "$version" == "True" ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python 3.11 or newer is required." >&2
    echo "Install from https://www.python.org/downloads/" >&2
    exit 1
fi
echo "Found Python: $($PYTHON --version)"

# --- Install canvas-tui if not present ---
if ! "$PYTHON" -c "import canvas_tui" 2>/dev/null; then
    echo "Installing canvas-tui from PyPI..."
    "$PYTHON" -m pip install --quiet canvas-tui
else
    echo "canvas-tui already installed."
fi

# --- Require environment variables ---
if [[ -z "${CANVAS_BASE_URL:-}" ]]; then
    echo ""
    echo "ERROR: CANVAS_BASE_URL is not set." >&2
    echo "  export CANVAS_BASE_URL=\"https://your-institution.instructure.com\"" >&2
    echo "  Get your Canvas base URL from your institution's Canvas login page." >&2
    exit 1
fi

if [[ -z "${CANVAS_TOKEN:-}" ]]; then
    echo ""
    echo "ERROR: CANVAS_TOKEN is not set." >&2
    echo "  export CANVAS_TOKEN=\"your_token\"" >&2
    echo "  Generate a token: Canvas -> Account -> Settings -> New Access Token" >&2
    exit 1
fi

echo ""
echo "Launching canvas-tui..."
echo "  Instance: $CANVAS_BASE_URL"
echo "  Token:    <set>"
echo ""
exec "$PYTHON" -m canvas_tui
