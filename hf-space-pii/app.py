# SPDX-License-Identifier: Apache-2.0
"""Canvas PII Scrub — FastAPI wrapper around iiiorg/piiranha-v1-detect-personal-information.

Public Space: kleinpanic93/canvas-pii-scrub
Endpoints: POST /scrub, POST /entities, GET /health, GET /
Rate limit: 30 req/min/IP (slowapi)
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

try:
    from transformers import pipeline as hf_pipeline

    _ner = hf_pipeline(
        "token-classification",
        model="iiiorg/piiranha-v1-detect-personal-information",
        aggregation_strategy="simple",
    )
    print("Piiranha loaded.", flush=True)
except Exception as _load_err:
    print(f"WARNING: Piiranha failed to load: {_load_err}", file=sys.stderr, flush=True)
    _ner = None


# ---------------------------------------------------------------------------
# Label maps and target fields — copied from anon_worker_piiranha.py
# ---------------------------------------------------------------------------

_PERSON_LABELS = {"I-GIVENNAME", "I-SURNAME", "I-USERNAME"}
_LOC_LABELS = {"I-CITY", "I-STREET", "I-BUILDINGNUM", "I-ZIPCODE"}

_TARGET_FIELDS = {"content", "text", "final_answer"}

_ROOM_PATTERN = re.compile(
    r"\b(?:Room\s+)?(?!(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Spring|Fall|Summer|Winter|Week|Chapter|Section|Unit|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b)"
    r"[A-Z][A-Za-z]+(?:\s+(?:Hall|Building|Lab|Center|Annex|Room))?"
    r"\s+\d{2,3}\b"
)

_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB


# ---------------------------------------------------------------------------
# Redaction logic — ported from anon_worker_piiranha.py, modified to return
# (doc, person_reg, loc_reg) so callers can build the registry response.
# ---------------------------------------------------------------------------

def _apply_room_regex(text: str, loc_reg: dict) -> list[tuple[int, int, str]]:
    replacements = []
    for m in _ROOM_PATTERN.finditer(text):
        raw = m.group()
        if "@COURSE" in raw:
            continue
        if raw not in loc_reg:
            loc_reg[raw] = f"@LOC_{len(loc_reg) + 1}"
        replacements.append((m.start(), m.end(), loc_reg[raw]))
    return replacements


def _anon_text(text: str, person_reg: dict, loc_reg: dict) -> str:
    if text.startswith("<|tool_call>"):
        return text

    replacements = _apply_room_regex(text, loc_reg)

    entities = _ner(text)
    for ent in entities:
        raw = ent["word"]
        label = ent["entity_group"]
        start = ent["start"]
        end = ent["end"]
        if "@COURSE" in raw:
            continue
        if any(s <= start < e for s, e, _ in replacements):
            continue
        if label in _PERSON_LABELS:
            if raw not in person_reg:
                person_reg[raw] = f"@PERSON_{len(person_reg) + 1}"
            replacements.append((start, end, person_reg[raw]))
        elif label in _LOC_LABELS:
            if raw not in loc_reg:
                loc_reg[raw] = f"@LOC_{len(loc_reg) + 1}"
            replacements.append((start, end, loc_reg[raw]))

    if not replacements:
        return text
    replacements.sort(key=lambda x: x[0], reverse=True)
    result = text
    for start, end, token in replacements:
        result = result[:start] + token + result[end:]
    return result


def _anon_value(value: Any, person_reg: dict, loc_reg: dict) -> Any:
    if isinstance(value, str):
        return _anon_text(value, person_reg, loc_reg)
    if isinstance(value, list):
        return [_anon_value(item, person_reg, loc_reg) for item in value]
    if isinstance(value, dict):
        return {k: (_anon_value(v, person_reg, loc_reg) if k in _TARGET_FIELDS else v)
                for k, v in value.items()}
    return value


def _anon_tool_result(tool_result: dict, person_reg: dict, loc_reg: dict) -> dict:
    content = tool_result.get("content")
    if not isinstance(content, str):
        return tool_result
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return {**tool_result, "content": _anon_text(content, person_reg, loc_reg)}
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                item["name"] = _anon_text(item["name"], person_reg, loc_reg)
    return {**tool_result, "content": json.dumps(parsed)}


def _anon_doc(doc: dict) -> tuple[dict, dict, dict]:
    """Redact PII from a document. Returns (scrubbed_doc, person_reg, loc_reg).

    person_reg and loc_reg map raw strings to @PERSON_N / @LOC_N tokens.
    Both registries reset per call — no cross-request state.
    """
    person_reg: dict[str, str] = {}
    loc_reg: dict[str, str] = {}

    if doc.get("type") == "course_snapshot":
        return doc, person_reg, loc_reg

    out: dict[str, Any] = {}
    for k, v in doc.items():
        if k in _TARGET_FIELDS:
            out[k] = _anon_value(v, person_reg, loc_reg)
        elif k == "tool_result" and isinstance(v, dict):
            out[k] = _anon_tool_result(v, person_reg, loc_reg)
        elif k == "messages" and isinstance(v, list):
            new_msgs = []
            for msg in v:
                if isinstance(msg, dict):
                    new_msg = {}
                    for mk, mv in msg.items():
                        if mk in _TARGET_FIELDS and isinstance(mv, str):
                            new_msg[mk] = _anon_text(mv, person_reg, loc_reg)
                        else:
                            new_msg[mk] = mv
                    new_msgs.append(new_msg)
                else:
                    new_msgs.append(msg)
            out[k] = new_msgs
        else:
            out[k] = v

    return out, person_reg, loc_reg


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ScrubRequest(BaseModel):
    document: dict


class ScrubResponse(BaseModel):
    document: dict
    redactions: list[dict]
    registry: dict


class EntitiesRequest(BaseModel):
    inputs: str


# ---------------------------------------------------------------------------
# Rate limiter (slowapi)
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Canvas PII Scrub",
    description=(
        "Public PII scrubbing service for CS3704-Canvas-Project contributors. "
        "Wraps iiiorg/piiranha-v1-detect-personal-information. No auth required. "
        "Rate limit: 30 req/min/IP."
    ),
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Body size limit middleware (T-04-01: 2 MB cap)
# ---------------------------------------------------------------------------

@app.middleware("http")
async def _body_size_limit(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and int(cl) > _MAX_BODY_BYTES:
        return Response(
            content=json.dumps({"error": "Request body exceeds 2 MB limit"}),
            status_code=413,
            media_type="application/json",
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# User-Agent logging middleware (D-10: log non-canvas-tracker UAs)
# ---------------------------------------------------------------------------

@app.middleware("http")
async def _ua_logger(request: Request, call_next):
    ua = request.headers.get("user-agent", "")
    if request.url.path not in ("/health", "/") and "canvas-tracker" not in ua:
        print(f"INFO non-canvas-tracker UA: {ua!r} path={request.url.path}", flush=True)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return """<!DOCTYPE html>
<html><head><title>Canvas PII Scrub</title></head><body>
<h1>Canvas PII Scrub</h1>
<p>Public PII scrubbing service for <a href="https://github.com/kleinpanic/CS3704-Canvas-Project">CS3704-Canvas-Project</a> contributors.
Wraps <code>iiiorg/piiranha-v1-detect-personal-information</code>.
No HuggingFace token required. Rate limit: 30 req/min/IP.</p>
<p>API docs: <a href="/docs">/docs</a></p>
</body></html>"""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/scrub", response_model=ScrubResponse)
async def scrub(body: ScrubRequest):
    if _ner is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    scrubbed, person_reg, loc_reg = _anon_doc(body.document)
    merged_reg = {**person_reg, **loc_reg}
    redactions = [{"token": token, "count": 1} for token in merged_reg.values()]
    return ScrubResponse(document=scrubbed, redactions=redactions, registry=merged_reg)


@app.post("/entities")
async def entities(body: EntitiesRequest):
    if _ner is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    raw_entities = _ner(body.inputs)
    return [
        {
            "entity_group": e["entity_group"],
            "score": float(e["score"]),
            "word": e["word"],
            "start": int(e["start"]),
            "end": int(e["end"]),
        }
        for e in raw_entities
    ]


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
