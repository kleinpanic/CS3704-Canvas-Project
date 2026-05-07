#!/usr/bin/env bash
set -euo pipefail

SPACE="${CANVAS_PII_SPACE_URL:-https://kleinpanic93-canvas-pii-scrub.hf.space}"
echo "Smoke-testing Space: $SPACE"

# /health
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SPACE/health")
[ "$CODE" = "200" ] || { echo "FAIL /health returned $CODE"; exit 1; }
echo "PASS /health"

# /scrub
RESP=$(curl -s -X POST "$SPACE/scrub" \
  -H "Content-Type: application/json" \
  -d '{"document": {"type": "todo_snapshot", "text": "Hello world"}}')
echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'document' in d, f'no document key: {d}'
print('PASS /scrub')
"

# /entities
RESP=$(curl -s -X POST "$SPACE/entities" \
  -H "Content-Type: application/json" \
  -d '{"inputs": "Hello world"}')
echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert isinstance(d, list), f'expected list: {d}'
print('PASS /entities (got', len(d), 'entities)')
"

echo "All smoke tests passed."
