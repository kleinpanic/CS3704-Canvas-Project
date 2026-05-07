# SPDX-License-Identifier: GPL-3.0-or-later
"""Purpose-built validator for data/collab/*.jsonl contributions.

Owned validator (no third-party action) for auditability; see D-06 in
.planning/phases/03-ci-dataset-validation-workflow/03-CONTEXT.md.

Usage:
  python tools/validate_collab_jsonl.py [--pii] [--piiranha-model-sha SHA] <files...>

Exit codes:
  0  All records pass.
  1  Validation failure (malformed JSON, schema violation, PII detected).
  2  Transient error (Piiranha unavailable when HF_TOKEN is set).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import canvas_tui.pii as _pii_mod
from canvas_tui.pii import SCRUB_KEYS, _piiranha_call, scrub_string

REQUIRED_KEYS = {"type", "contributor_id", "collected_at", "course_code"}
FORBIDDEN_KEYS = {"course_name"}

COURSE_CODE_RE = re.compile(r"^@COURSE\d+/")


def _validate_file(path: str, pii_mode: bool, hf_token: str, space_url: str = "") -> int:
    try:
        fh = open(path, encoding="utf-8")
    except OSError as e:
        print(f"FAIL {path}: cannot open — {e}")
        return 1

    with fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue

            # PARSE
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"FAIL {path}:{lineno}: invalid JSON — {e}")
                return 1

            if not isinstance(record, dict):
                print(f"FAIL {path}:{lineno}: record is not a JSON object")
                return 1

            # SCHEMA
            for key in REQUIRED_KEYS:
                if key not in record:
                    print(f"FAIL {path}:{lineno}: missing required field '{key}'")
                    return 1
                if not isinstance(record[key], str):
                    print(f"FAIL {path}:{lineno}: field '{key}' must be a string")
                    return 1

            for key in FORBIDDEN_KEYS:
                if key in record:
                    print(
                        f"FAIL {path}:{lineno}: forbidden field '{key}' present "
                        f"— run: python scripts/share_my_canvas.py --dry-run"
                    )
                    return 1

            course_code = record["course_code"]
            if course_code and not COURSE_CODE_RE.match(course_code):
                print(
                    f"FAIL {path}:{lineno}: non-anonymized course_code '{course_code}' "
                    f"— run: python scripts/share_my_canvas.py --dry-run"
                )
                return 1

            # PII
            if pii_mode:
                if space_url:
                    from canvas_tui.pii import scrub_via_space
                    for key, value in record.items():
                        if key not in SCRUB_KEYS or not isinstance(value, str):
                            continue
                        resp = scrub_via_space({"text": value}, space_url)
                        scrubbed = resp.get("text", value)
                        if scrubbed != value:
                            print(
                                f"FAIL {path}:{lineno}: PII detected in '{key}' "
                                f"— run: python scripts/share_my_canvas.py --dry-run"
                            )
                            return 1
                else:
                    for key, value in record.items():
                        if key not in SCRUB_KEYS or not isinstance(value, str):
                            continue
                        if hf_token:
                            piiranha_result = _piiranha_call(value, hf_token)
                            if piiranha_result is None:
                                print(
                                    "ERROR: Piiranha unavailable (transient) — "
                                    "re-run the workflow or contact maintainer"
                                )
                                return 2
                        scrubbed = scrub_string(value, hf_token=hf_token)
                        if scrubbed != value:
                            print(
                                f"FAIL {path}:{lineno}: PII detected in '{key}' "
                                f"— run: python scripts/share_my_canvas.py --dry-run"
                            )
                            return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate data/collab/*.jsonl files for schema and PII compliance."
    )
    parser.add_argument("files", nargs="+", help="JSONL file paths to validate")
    parser.add_argument("--pii", action="store_true", help="Enable PII scan mode")
    parser.add_argument(
        "--piiranha-model-sha",
        metavar="SHA",
        help="Override PIIRANHA_URL to a pinned model revision",
    )
    parser.add_argument(
        "--space-url",
        metavar="URL",
        help="Canvas PII Space URL. When set, call /scrub instead of local Piiranha.",
    )
    args = parser.parse_args()

    if args.space_url and args.piiranha_model_sha:
        print("ERROR: --space-url and --piiranha-model-sha are mutually exclusive")
        sys.exit(1)

    if args.piiranha_model_sha:
        base = "https://api-inference.huggingface.co/models/iiiorg/piiranha-v1-detect-personal-information"
        _pii_mod.PIIRANHA_URL = f"{base}/resolve/{args.piiranha_model_sha}"

    hf_token = os.environ.get("HF_TOKEN", "") if args.pii else ""
    space_url = args.space_url or ""
    total = 0

    for path in args.files:
        code = _validate_file(path, pii_mode=args.pii, hf_token=hf_token, space_url=space_url)
        if code != 0:
            sys.exit(code)
        with open(path, encoding="utf-8") as fh:
            total += sum(1 for line in fh if line.strip())

    print(f"OK: {total} records validated")


if __name__ == "__main__":
    main()
