#!/usr/bin/env bash
set -euo pipefail
rm -rf build/ dist/ src/canvas_tui.egg-info/ src/sdk/dist/ src/sdk/build/ \
       .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
echo "cleaned"
