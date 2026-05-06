# Cloudflare Worker proxy — GH Pages → HF Space

Holds the HF_TOKEN server-side. Browsers only see the proxy URL.

## One-time deploy

```bash
# 1. Install wrangler
npm install -g wrangler

# 2. Log in (opens browser)
wrangler login

# 3. From this directory
cd proxy
wrangler deploy

# 4. Set the HF token as a secret (NOT in code, NOT in wrangler.toml)
wrangler secret put HF_TOKEN
# (paste the token when prompted)
```

The worker will be live at `https://cs3704-demo-proxy.kleinpanic.workers.dev`.

## Update on changes

```bash
wrangler deploy   # redeploys worker.js
```

## Test

```bash
curl -X POST https://cs3704-demo-proxy.kleinpanic.workers.dev/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is due this week?"}'
```

Expected response shape:
```json
{
  "final_answer": "...",
  "tool_calls": [
    {"tool":"canvas.get_assignments","args":{},"result":{"items":[...]}}
  ]
}
```

## What this protects against

- HF_TOKEN never reaches the browser → cannot be extracted from public JS.
- Token can be any scope (no need to scope down) since it stays server-side.
- CORS whitelist limits which origins can use the proxy (`kleinpanic.github.io` + localhost).
- Body validation rejects empty / oversize requests before paying for an HF call.

## Free tier limits

- 100,000 requests/day on Cloudflare's free tier.
- 10ms CPU per request (the heavy lifting is on HF Space, not the worker).
- More than enough for a class demo.

## Rotation

If the HF_TOKEN ever leaks (it shouldn't — it lives only as a Cloudflare secret), rotate by:

```bash
# Revoke old token at https://huggingface.co/settings/tokens
# Generate new one
wrangler secret put HF_TOKEN
# (paste new token)
```

No code change needed.
