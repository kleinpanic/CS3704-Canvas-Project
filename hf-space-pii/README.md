---
title: Canvas PII Scrub
emoji: 🔒
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Piiranha-v1 PII scrubber for Canvas dataset PRs
---

# Canvas PII Scrub

Public PII scrubbing service for [CS3704-Canvas-Project](https://github.com/kleinpanic/CS3704-Canvas-Project) contributors.
Wraps [iiiorg/piiranha-v1-detect-personal-information](https://huggingface.co/iiiorg/piiranha-v1-detect-personal-information)
in a FastAPI app. **No HuggingFace token required** — the Space is public and free to call.
Used by `scripts/share_my_canvas.py --scrub-via-space` and the CI dataset-validation pipeline.

## API

### POST /scrub

Scrub PII from a single Canvas dataset document.

**Request:** `{"document": <obj>}`

**Response:** `{"document": <scrubbed_obj>, "redactions": [{"token": "@PERSON_1", "count": 1}], "registry": {"Alice": "@PERSON_1"}}`

**Errors:** `503` model not loaded; `413` body > 2 MB; `429` rate limit exceeded.

### POST /entities

HuggingFace Inference API-compatible entity detection shim.

**Request:** `{"inputs": "<text string>"}`

**Response:** `[{"entity_group": "I-EMAIL", "score": 0.99, "word": "...", "start": 12, "end": 30}]`

Drop-in replacement for the HF Inference API URL (same request/response shape).

### GET /health

Warmup check. Returns `{"status": "ok"}` with 200 when the model is loaded.

## Rate Limits

30 requests per minute per IP. Exceeding this returns 429.
The limit is intentionally generous — single-contributor scripts are well below it.

## Cold Start

Free-tier CPU Spaces sleep after 48h idle. First request may take 30-60s to wake.
CI uses `GET /health` as a warmup ping before submitting documents.

## Self-Host

For offline or fork contributors, you can run the Space locally:

```bash
docker build -t canvas-pii-scrub .
docker run -p 7860:7860 canvas-pii-scrub
```

Self-host is out of scope for Phase 4 of the project — see the project repo for the roadmap.
