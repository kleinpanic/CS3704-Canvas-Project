# SPDX-License-Identifier: GPL-3.0-or-later
"""PII scrubbing for Canvas dataset contributions."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ADDR_RE = re.compile(
    r"\b\d{1,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Court|Ct|Lane|Ln)\b"
)

SCRUB_KEYS = {
    "name",
    "title",
    "description",
    "message",
    "body",
    "syllabus_body",
    "content",
    "summary",
    "details",
    "course_name",
    "short_name",
    "original_name",
}

_piiranha_available = True

PIIRANHA_URL = "https://api-inference.huggingface.co/models/iiiorg/piiranha-v1-detect-personal-information"

CANVAS_PII_SPACE_URL = os.environ.get(
    "CANVAS_PII_SPACE_URL",
    "https://kleinpanic93-canvas-pii-scrub.hf.space",
)


def _piiranha_call(text: str, hf_token: str) -> str | None:
    """Call Piiranha via HF Inference API. Returns redacted text or None on any error."""
    global _piiranha_available
    if not _piiranha_available:
        return None
    payload = json.dumps({"inputs": text}).encode()
    req = urllib.request.Request(
        PIIRANHA_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            entities = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 503:
            print("  Piiranha: model loading (503), retrying in 5 s…", file=sys.stderr)
            time.sleep(5)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    entities = json.loads(resp.read())
            except Exception as retry_err:
                print(f"  Piiranha: retry failed ({retry_err}), falling back to regex", file=sys.stderr)
                _piiranha_available = False
                return None
        else:
            print(f"  Piiranha: HTTP {e.code}, falling back to regex", file=sys.stderr)
            _piiranha_available = False
            return None
    except Exception as e:
        print(f"  Piiranha: {e}, falling back to regex", file=sys.stderr)
        _piiranha_available = False
        return None

    if not isinstance(entities, list):
        return None

    chars = list(text)
    for ent in sorted(entities, key=lambda x: x.get("start", 0), reverse=True):
        start = ent.get("start")
        end = ent.get("end")
        group = ent.get("entity_group", "PII")
        if start is None or end is None:
            continue
        chars[start:end] = list(f"[{group}]")
    return "".join(chars)


def _regex_fallback(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = SSN_RE.sub("[SSN]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    text = ADDR_RE.sub("[ADDRESS]", text)
    return text


def scrub_string(text: str, *, hf_token: str = "") -> str:
    """Scrub a single string: Piiranha-first (if hf_token set), regex fallback."""
    if not isinstance(text, str):
        return text
    if hf_token and len(text) > 20:
        result = _piiranha_call(text, hf_token)
        if result is not None:
            return result
    return _regex_fallback(text)


def scrub_doc(
    obj: object,
    *,
    hf_token: str = "",
    mode: str = "piiranha-then-regex",
    scrub_method: str = "local-piiranha",
    space_url: str | None = None,
) -> object:
    """Recursively scrub PII from a document (dict, list, or string)."""
    if scrub_method == "space":
        if space_url is None:
            raise ValueError("space_url required when scrub_method='space'")
        doc = obj if isinstance(obj, dict) else {"_root": obj}
        return scrub_via_space(doc, space_url)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in SCRUB_KEYS and isinstance(v, str):
                out[k] = scrub_string(v, hf_token=hf_token)
            else:
                out[k] = scrub_doc(v, hf_token=hf_token, mode=mode)
        return out
    if isinstance(obj, list):
        return [scrub_doc(x, hf_token=hf_token, mode=mode) for x in obj]
    if isinstance(obj, str):
        return scrub_string(obj, hf_token=hf_token)
    return obj


def scrub_via_space(doc: dict, space_url: str) -> dict:
    """POST doc to the canvas-pii-scrub Space /scrub endpoint.

    Returns the scrubbed document dict on success.
    Falls back to scrub_doc(doc) on connection error or non-200 after retry.
    """
    payload = json.dumps({"document": doc}).encode()
    req = urllib.request.Request(
        f"{space_url}/scrub",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "canvas-tracker/share_my_canvas",
        },
        method="POST",
    )

    def _fallback(reason: str) -> dict:
        print(f"  scrub_via_space: {reason} — falling back to local scrub", file=sys.stderr)
        return scrub_doc(doc)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["document"]
    except urllib.error.HTTPError as e:
        if e.code == 503:
            retry_after = int(e.headers.get("Retry-After", 30)) if e.headers else 30
            print(
                f"  scrub_via_space: 503 (Space cold-start), retrying in {retry_after}s…",
                file=sys.stderr,
            )
            time.sleep(retry_after)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read())["document"]
            except Exception as retry_err:
                return _fallback(f"retry failed ({retry_err})")
        return _fallback(f"HTTP {e.code}")
    except urllib.error.URLError as e:
        return _fallback(f"URLError {e.reason}")
    except Exception as e:
        return _fallback(str(e))


__all__ = ["SCRUB_KEYS", "scrub_doc", "scrub_string", "scrub_via_space", "CANVAS_PII_SPACE_URL"]
