#!/bin/bash
# Deploy the Cloudflare Worker proxy WITHOUT installing wrangler.
# Uses Cloudflare's REST API directly — works from any machine with curl + bash.
#
# One-time setup (do this once on https://dash.cloudflare.com):
#   1. Sign up (free)
#   2. Note your Account ID (right side of the dashboard home page)
#   3. Create an API token: My Profile > API Tokens > Create Token
#      Use template "Edit Cloudflare Workers" — that has all needed permissions
#   4. Export both:
#        export CF_ACCOUNT_ID="your-account-id"
#        export CF_API_TOKEN="your-api-token"
#        export HF_TOKEN="hf_..."
#
# Then run: bash deploy-curl.sh
#
# After deploy, the worker is live at:
#   https://cs3704-demo-proxy.<your-subdomain>.workers.dev
# Update PROXY_URL in chrome_shim_prod.js + agent-demo/index.html to match.

set -euo pipefail

: "${CF_ACCOUNT_ID:?missing CF_ACCOUNT_ID env}"
: "${CF_API_TOKEN:?missing CF_API_TOKEN env}"
: "${HF_TOKEN:?missing HF_TOKEN env}"

SCRIPT_NAME="cs3704-demo-proxy"
SCRIPT_FILE="$(dirname "$0")/worker.js"
API="https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${SCRIPT_NAME}"

echo "[1/3] Uploading worker.js to Cloudflare..."
# Multipart upload (the modern Cloudflare API requires metadata + script)
RESP=$(curl -sS -X PUT "$API" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -F "metadata={\"main_module\":\"worker.js\",\"compatibility_date\":\"2026-05-05\"};type=application/json" \
  -F "worker.js=@${SCRIPT_FILE};type=application/javascript+module")
echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  result:', 'OK' if d.get('success') else d.get('errors'))"

echo "[2/3] Setting HF_TOKEN secret..."
curl -sS -X PUT "${API}/secrets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"HF_TOKEN\",\"text\":\"${HF_TOKEN}\",\"type\":\"secret_text\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('  result:', 'OK' if d.get('success') else d.get('errors'))"

echo "[3/3] Enabling workers.dev subdomain route..."
curl -sS -X POST "${API}/subdomain" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('  result:', 'OK' if d.get('success') else d.get('errors'))" || true

# Discover the subdomain so we can print the URL
SUB=$(curl -sS -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/subdomain" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('subdomain','<unknown>'))")
echo
echo "Worker live at: https://${SCRIPT_NAME}.${SUB}.workers.dev"
echo
echo "Update PROXY_URL in:"
echo "  docs-site/chrome_shim_prod.js:14"
echo "  docs-site/agent-demo/index.html  (around line 455)"
echo "if your subdomain isn't 'kleinpanic'."
echo
echo "Quick test:"
echo "  curl -X POST https://${SCRIPT_NAME}.${SUB}.workers.dev/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"message\":\"What is due this week?\"}'"
