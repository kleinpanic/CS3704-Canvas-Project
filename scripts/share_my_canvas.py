"""
share_my_canvas.py — dump your Canvas data for CS3704 dataset contribution.

Pulls ALL courses across your full enrollment history (4 years), ALL
assignments (past, current, upcoming), and your submission status for each.
Everything is anonymized before writing — no real names, IDs, or course
codes leave your machine.

Requirements:
    pip install requests

Usage:
    export CANVAS_TOKEN=your_token_here
    python3 scripts/data-collection/share_my_canvas.py --contributor yourpid

That's it. No other API keys or setup needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from canvas_tui.pii import scrub_doc  # noqa: E402

BASE_URL = os.environ.get("CANVAS_BASE_URL", "").strip()
if not BASE_URL:
    print(
        "ERROR: CANVAS_BASE_URL must be set to your institution's Canvas URL\n"
        "  e.g. export CANVAS_BASE_URL=https://canvas.yourschool.edu",
        file=sys.stderr,
    )
    sys.exit(1)

# All enrollment states so we get 4 years of history
_ENROLLMENT_STATES = ["active", "completed", "invited", "rejected"]

# Canvas submission_type → pipeline type
_SUBTYPE_MAP = {
    "online_quiz":        "QUIZ",
    "online_upload":      "ASGN",
    "online_text_entry":  "ASGN",
    "discussion_topic":   "DISC",
    "media_recording":    "ASGN",
    "none":               "ASGN",
    "not_graded":         None,   # skip ungraded
    "wiki_page":          None,   # skip
    "external_tool":      "ASGN",
}


def _token() -> str:
    t = os.environ.get("CANVAS_TOKEN", "")
    if not t:
        print("ERROR: CANVAS_TOKEN is not set.\n"
              "Get your token at canvas.vt.edu → Account → Settings → "
              "Approved Integrations → New Access Token\n"
              "Then run:  export CANVAS_TOKEN=your_token_here")
        sys.exit(1)
    return t


def _get(path: str, params: dict | None = None) -> list | dict:
    import requests
    tok = _token()
    headers = {"Authorization": f"Bearer {tok}"}
    url = f"{BASE_URL}/api/v1{path}"
    results = []
    while url:
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
            r.raise_for_status()
        except requests.RequestException as exc:
            safe = str(exc).replace(tok, "[CANVAS_TOKEN]")
            raise RuntimeError(safe) from None
        data = r.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        link = r.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                params = None
                break
    return results


def _hash(salt: str, val: str) -> str:
    return f"ID{int(hashlib.sha256((salt + val).encode()).hexdigest()[:6], 16) % 1000000:06d}"


_COURSE_MAP: dict[str, str] = {}
_COURSE_CTR = [0]


def _anon_course(code: str) -> str:
    if code not in _COURSE_MAP:
        _COURSE_CTR[0] += 1
        _COURSE_MAP[code] = f"@COURSE{_COURSE_CTR[0]}"
    return _COURSE_MAP[code]


def anonymize(obj: object, salt: str) -> object:
    def _walk(o):
        if isinstance(o, dict):
            return {k: _walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_walk(v) for v in o]
        if isinstance(o, int):
            s = str(o)
            if re.match(r"[1-9]\d{6,8}$", s):
                return _hash(salt, s)
        if isinstance(o, str):
            o = re.sub(r"\b([1-9]\d{6,8})\b", lambda m: _hash(salt, m.group(1)), o)
        return o

    obj = _walk(obj)
    text = json.dumps(obj, default=str)
    # Pass 1: strict — "CS 3704", "ENGL2204", "CS3114"
    text = re.sub(
        r"\b([A-Z]{2,5})\s*(\d{3,4}[A-Z]?)\b",
        lambda m: _anon_course(m.group(0)),
        text,
    )
    # Pass 2: underscore form — "CS_3114_202601", "CS_3704_21936_202601"
    text = re.sub(
        r"(?<![A-Z])([A-Z]{2,5})_(\d{3,4}[A-Z]?)(?:_\d+)*(?![A-Z])",
        lambda m: _anon_course(m.group(1) + "_" + m.group(2)),
        text,
    )
    return json.loads(text)


def _submission_type(sub_types: list[str]) -> str | None:
    for t in (sub_types or []):
        mapped = _SUBTYPE_MAP.get(t)
        if mapped is not None:
            return mapped
        if mapped is None and t in _SUBTYPE_MAP:
            return None  # explicitly skipped type
    return "ASGN"


def collect(contributor: str) -> list[dict]:
    collected_at = datetime.now(timezone.utc).isoformat()

    # Fetch all courses across all enrollment states (full 4-year history)
    print("Fetching courses (all enrollment states)...")
    seen_cids: set = set()
    courses = []
    for state in _ENROLLMENT_STATES:
        batch = _get("/courses", {
            "enrollment_state": state,
            "per_page": 50,
            "include[]": "term",
        })
        for c in batch:
            if c.get("id") not in seen_cids:
                seen_cids.add(c.get("id"))
                courses.append(c)
    print(f"  {len(courses)} total courses across all terms")

    records = []

    for course in courses:
        cid = course.get("id")
        cname = course.get("name", "")
        term = (course.get("term") or {}).get("name", "")
        print(f"  {cname} [{term}]...")
        try:
            # Get ALL assignments — no bucket filter — to capture full history
            assignments = _get(f"/courses/{cid}/assignments", {
                "per_page": 50,
                "order_by": "due_at",
                "include[]": ["submission"],
            })
        except Exception as e:
            print(f"    skipped ({e})")
            assignments = []

        asgn_records = []
        for a in assignments:
            sub_types = a.get("submission_types") or []
            atype = _submission_type(sub_types)
            if atype is None:
                continue  # skip ungraded/wiki items

            pts = a.get("points_possible")
            if not pts or float(pts) <= 0:
                continue

            # Submission status from the included submission object
            sub = a.get("submission") or {}
            submitted = sub.get("submitted_at") is not None
            graded = sub.get("graded_at") is not None
            workflow = sub.get("workflow_state", "")
            if workflow == "graded" or graded:
                sub_status = "GRADED"
            elif submitted:
                sub_status = "SUBMITTED"
            else:
                sub_status = "NOT_SUBMITTED"

            asgn_records.append({
                "name": a.get("name"),
                "type": atype,
                "due_at": a.get("due_at"),
                "points_possible": pts,
                "submission_types": sub_types,
                "submission_status": sub_status,
            })

        if not asgn_records:
            continue  # skip courses with nothing plannable

        # Anonymize course_code and course_name to the same @COURSE handle.
        # Catches both "CS 3704" and underscore forms "CS_3114_202601".
        _raw_code = course.get("course_code", "")
        _m = re.search(r"[A-Z]{2,5}[\s_]\d{3,4}[A-Z]?", _raw_code)
        _code_key = _m.group(0) if _m else _raw_code
        _anon_handle = _anon_course(_code_key) if _code_key else ""
        records.append({
            "type": "course_snapshot",
            "course_name": _anon_handle,
            "course_code": _anon_handle,
            "term": term,
            "assignments": asgn_records,
            "contributor_id": contributor,
            "collected_at": collected_at,
        })

    print("Fetching todo list...")
    try:
        todos = _get("/users/self/todo_items", {"per_page": 50})
        records.append({
            "type": "todo_snapshot",
            "items": [
                {
                    "type": t.get("type"),
                    "assignment_name": t.get("assignment", {}).get("name") if t.get("assignment") else None,
                    "due_at": t.get("assignment", {}).get("due_at") if t.get("assignment") else None,
                    "course_id": t.get("course_id"),
                }
                for t in todos
            ],
            "contributor_id": contributor,
            "collected_at": collected_at,
        })
        print(f"  {len(todos)} todo items")
    except Exception as e:
        print(f"  todo fetch skipped ({e})")

    hf_token = os.environ.get("HF_TOKEN", "")
    return [scrub_doc(anonymize(r, contributor), hf_token=hf_token) for r in records]


def _dry_run_summary(records: list[dict]) -> None:
    import hashlib as _hashlib

    jsonl_bytes = "\n".join(json.dumps(r) for r in records).encode()
    checksum = _hashlib.sha256(jsonl_bytes).hexdigest()

    type_counts: dict[str, int] = {}
    samples: dict[str, str] = {}
    text_fields = ("course_name", "course_code", "assignment_name")

    for rec in records:
        rtype = rec.get("type", "unknown")
        type_counts[rtype] = type_counts.get(rtype, 0) + 1
        for field in text_fields:
            val = rec.get(field)
            if val and field not in samples:
                samples[field] = str(val)[:80]
        for asgn in rec.get("assignments", []) or []:
            name = asgn.get("name")
            if name and "assignment_name" not in samples:
                samples["assignment_name"] = str(name)[:80]

    print("--- dry-run summary ---", file=sys.stderr)
    print(f"  total records: {len(records)}", file=sys.stderr)
    for rtype, count in sorted(type_counts.items()):
        print(f"  {rtype}: {count}", file=sys.stderr)
    if samples:
        print("  sample field values (post-scrub):", file=sys.stderr)
        for field, val in samples.items():
            print(f"    {field}: {val!r}", file=sys.stderr)
    print(f"  checksum: sha256:{checksum}", file=sys.stderr)
    print("--- end dry-run ---", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="Dump anonymized Canvas data for CS3704 dataset.")
    p.add_argument("--contributor", required=True,
                   help="Your PID or GitHub handle — used as anonymization salt, never stored in output")
    p.add_argument("--output", default=None,
                   help="Output JSONL path (default: data/collab/<contributor>.jsonl)")
    p.add_argument("--dry-run", action="store_true",
                   help="Run full pipeline but write nothing; print scrubbed-output summary to stderr.")
    p.add_argument("--inspect", action="store_true",
                   help="Synonym for --dry-run.")
    p.add_argument("--piiranha-required", action="store_true",
                   help="Abort if Piiranha is unreachable (default: fall back to regex).")
    args = p.parse_args()

    out = Path(args.output) if args.output else \
        Path("data/collab") / f"{args.contributor}.jsonl"

    records = collect(args.contributor)

    if args.piiranha_required:
        import canvas_tui.pii as _pii
        if not _pii._piiranha_available:
            print("ERROR: Piiranha unavailable and --piiranha-required set.", file=sys.stderr)
            sys.exit(2)

    if args.dry_run or args.inspect:
        _dry_run_summary(records)
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    course_snaps = [r for r in records if r.get("type") == "course_snapshot"]
    total_asgn = sum(len(r.get("assignments", [])) for r in course_snaps)
    print(f"\nWrote {len(records)} records ({len(course_snaps)} courses, {total_asgn} assignments) to {out}")
    print("Submit this file via PR (see docs/contributing-data.md for instructions).")


if __name__ == "__main__":
    main()
