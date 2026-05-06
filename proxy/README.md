# Cloudflare Worker proxy — GH Pages → HF Space + Canvas API

Holds `HF_TOKEN` and `CANVAS_TOKEN` server-side. Browsers only see the proxy URL.

## One-time deploy

```bash
# 1. Install wrangler
npm install -g wrangler

# 2. Log in (opens browser)
wrangler login

# 3. From this directory
cd proxy
wrangler deploy

# 4. Set secrets (NOT in code, NOT in wrangler.toml)
wrangler secret put HF_TOKEN
wrangler secret put CANVAS_TOKEN
# (paste each token when prompted)
```

The worker will be live at `https://cs3704-demo-proxy.kleinpanic.workers.dev`.

## Update on changes

```bash
wrangler deploy   # redeploys worker.js
```

## Routes

### POST /chat

Proxies a message to the HuggingFace Space demo agent.

Request body: `{ "message": string }` (max 4000 chars)

Response: `{ "final_answer": string, "tool_calls": [...] }`

```bash
curl -X POST https://cs3704-demo-proxy.kleinpanic.workers.dev/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is due this week?"}'
```

### POST /canvas

Proxies a Canvas API call to `https://canvas.vt.edu` with server-side auth.
Used by the live demo iframe — the extension in its native context still uses
the user's own stored token directly.

Request body:
```json
{
  "endpoint": "/api/v1/courses",
  "method": "GET",
  "body": null
}
```

- `endpoint` must start with `/api/v1/` (enforced; rejects anything else)
- `method` defaults to `GET`; allowed values: GET, POST, PUT, PATCH, DELETE
- `body` is optional; serialized size capped at 4000 chars
- Canvas's HTTP status code is forwarded as-is (401, 404, etc.)
- By default the response JSON is scrubbed for PII (emails, phone numbers, SSNs,
  street addresses) before being returned to the caller. This is defense-in-depth —
  the live demo does not currently route through this path, but if it ever does,
  PII won't leak.
- Append `?nopiiscrub=1` to opt out of scrubbing if you need raw field values
  (e.g. an extension author building their own UI that displays full names).

```bash
curl -X POST https://cs3704-demo-proxy.kleinpanic.workers.dev/canvas \
  -H "Content-Type: application/json" \
  -d '{"endpoint":"/api/v1/courses","method":"GET"}'
```

## What this protects against

- `HF_TOKEN` and `CANVAS_TOKEN` never reach the browser → cannot be extracted from public JS.
- Tokens can be any scope (no need to scope down) since they stay server-side.
- CORS whitelist limits which origins can use the proxy (`kleinpanic.github.io` + localhost).
- Body validation rejects empty / oversize requests before paying for an upstream call.
- `/canvas` enforces `/api/v1/` prefix on `endpoint` to prevent SSRF against arbitrary URLs.

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
