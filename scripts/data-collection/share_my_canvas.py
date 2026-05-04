"""
share_my_canvas.py — dump your Canvas data for CS3704 dataset contribution.

Pulls your courses, assignments, and todo list from VT Canvas, anonymizes
everything, and writes a JSONL file you can submit to the project.

Requirements:
    pip install requests

Usage:
    export CANVAS_TOKEN=your_token_here
    python3 scripts/share_my_canvas.py --contributor yourpid

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


BASE_URL = os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu")


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
    headers = {"Authorization": f"Bearer {_token()}"}
    url = f"{BASE_URL}/api/v1{path}"
    results = []
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        # follow Canvas pagination
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
        _COURSE_MAP[code] = f"COURSE{_COURSE_CTR[0]}"
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
    # Course codes like "CS 3704", "ENGL2204"
    text = re.sub(
        r"\b([A-Z]{2,5})\s*(\d{3,4}[A-Z]?)\b",
        lambda m: _anon_course(m.group(0)),
        text,
    )
    return json.loads(text)


def collect(contributor: str) -> list[dict]:
    print("Fetching courses...")
    courses = _get("/courses", {"enrollment_state": "active", "per_page": 50})
    print(f"  {len(courses)} active courses")

    records = []

    for course in courses:
        cid = course.get("id")
        cname = course.get("name", "")
        print(f"  Fetching assignments for {cname}...")
        try:
            assignments = _get(f"/courses/{cid}/assignments", {
                "per_page": 50,
                "order_by": "due_at",
                "bucket": "upcoming",
            })
        except Exception as e:
            print(f"    skipped ({e})")
            assignments = []

        records.append({
            "type": "course_snapshot",
            "course_name": cname,
            "course_code": course.get("course_code", ""),
            "assignments": [
                {
                    "name": a.get("name"),
                    "due_at": a.get("due_at"),
                    "points_possible": a.get("points_possible"),
                    "submission_types": a.get("submission_types"),
                }
                for a in assignments
            ],
            "contributor_id": contributor,
            "collected_at": datetime.now(timezone.utc).isoformat(),
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
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"  {len(todos)} todo items")
    except Exception as e:
        print(f"  todo fetch skipped ({e})")

    return [anonymize(r, contributor) for r in records]


def main():
    p = argparse.ArgumentParser(description="Dump anonymized Canvas data for CS3704 dataset.")
    p.add_argument("--contributor", required=True,
                   help="Your PID or GitHub handle — used as anonymization salt, never stored in output")
    p.add_argument("--output", default=None,
                   help="Output JSONL path (default: data/trajectories/collab/<contributor>.jsonl)")
    args = p.parse_args()

    out = Path(args.output) if args.output else \
        Path("data/trajectories/collab") / f"{args.contributor}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    records = collect(args.contributor)

    with open(out, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"\nWrote {len(records)} records to {out}")
    print("Submit this file via PR or email to rodie105@gmail.com")


if __name__ == "__main__":
    main()
