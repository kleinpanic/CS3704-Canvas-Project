#!/usr/bin/env python3
"""
CI script: pre-fetch Canvas API data and save as static JSON for the live demo.

Usage:
  CANVAS_TOKEN=<token> python3 docs-site/fetch_canvas_data.py --out site/data
  python3 docs-site/fetch_canvas_data.py --self-test   # regex sanity check, no network

Output files (all in --out dir):
  courses.json
  upcoming.json
  todo.json
  planner_notes.json
  course_<id>_assignments.json
  course_<id>_announcements.json
  course_<id>_modules.json
  course_<id>_grades.json

PII scrubbing: by default, every payload is run through scrub_recursive() before
being written to disk. The data baked into site/data/*.json is deployed to a
PUBLIC GitHub Pages site, so live Canvas content (assignment titles, descriptions,
announcement bodies, syllabus text) is regex-redacted for emails, phone numbers,
SSNs, and street addresses. Pass --no-scrub for local debugging only.
TODO: upgrade to a model-based scrub (e.g. iiiorg/piiranha) if the false-negative
rate of these regexes becomes a concern.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

CANVAS_BASE = "https://canvas.vt.edu/api/v1"
TOKEN = os.environ.get("CANVAS_TOKEN") or os.environ.get("CANVAS_API_TOKEN", "")

# ── PII scrub ────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
SSN_RE   = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ADDR_RE  = re.compile(
    r"\b\d{1,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Court|Ct|Lane|Ln)\b"
)

SCRUB_KEYS = {
    "name", "title", "description", "message", "body",
    "syllabus_body", "content", "summary", "details",
    "course_name", "short_name", "original_name",
}


def scrub(text):
    if not isinstance(text, str):
        return text
    text = SSN_RE.sub("[SSN]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    text = ADDR_RE.sub("[ADDRESS]", text)
    return text


def scrub_recursive(obj, target_keys=SCRUB_KEYS):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in target_keys and isinstance(v, str):
                out[k] = scrub(v)
            else:
                out[k] = scrub_recursive(v, target_keys)
        return out
    if isinstance(obj, list):
        return [scrub_recursive(x, target_keys) for x in obj]
    if isinstance(obj, str):
        # belt-and-braces: catch PII anywhere, even outside whitelisted keys
        return scrub(obj)
    return obj


def fetch(path, params=None):
    url = f"{CANVAS_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {path}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  Error {e} for {path}", file=sys.stderr)
        return []


def save(out_dir: Path, filename: str, data):
    path = out_dir / filename
    with open(path, "w") as f:
        json.dump({"ok": True, "data": data}, f)
    print(f"  wrote {path} ({len(data) if isinstance(data, list) else '...'} items)")


def self_test():
    sample = {
        "name": "Email Prof at jane@vt.edu about HW",
        "description": "Call 540-555-1234 or visit 123 Main Street",
        "courses": [{"description": "SSN 123-45-6789 mentioned"}],
        "nested": {"body": "Reach me: foo@bar.com / (703) 555-9999"},
    }
    cleaned = scrub_recursive(sample)
    assert "[EMAIL]" in cleaned["name"], cleaned
    assert "jane@vt.edu" not in json.dumps(cleaned), cleaned
    assert "[PHONE]" in cleaned["description"], cleaned
    assert "[ADDRESS]" in cleaned["description"], cleaned
    assert "[SSN]" in cleaned["courses"][0]["description"], cleaned
    assert "[EMAIL]" in cleaned["nested"]["body"], cleaned
    assert "[PHONE]" in cleaned["nested"]["body"], cleaned
    print("scrub self-test PASSED")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data", help="Output directory")
    ap.add_argument("--no-scrub", action="store_true",
                    help="Skip PII scrubbing (LOCAL DEBUG ONLY — never use in CI)")
    ap.add_argument("--self-test", action="store_true",
                    help="Run regex self-test and exit (no network calls)")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if not TOKEN:
        print("ERROR: CANVAS_TOKEN or CANVAS_API_TOKEN env var not set", file=sys.stderr)
        sys.exit(1)

    if args.no_scrub:
        print("WARNING: --no-scrub set; output will contain raw PII.", file=sys.stderr)
        clean = lambda x: x  # noqa: E731
    else:
        clean = scrub_recursive

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching courses...")
    courses = fetch("/courses", {"enrollment_state": "active", "per_page": "50"})
    save(out_dir, "courses.json", clean(courses))

    print("Fetching upcoming assignments...")
    upcoming = fetch("/users/self/upcoming_events", {"per_page": "50"})
    if not upcoming:
        upcoming = fetch("/users/self/calendar_events", {"type": "assignment", "per_page": "50"})
    save(out_dir, "upcoming.json", clean(upcoming))

    print("Fetching todo...")
    todo = fetch("/users/self/todo", {"per_page": "50"})
    save(out_dir, "todo.json", clean(todo))

    print("Fetching dashboard cards...")
    cards = fetch("/dashboard/dashboard_cards")
    save(out_dir, "dashboard_cards.json", clean(cards if isinstance(cards, list) else []))

    print("Fetching planner notes...")
    notes = fetch("/planner/items", {"per_page": "50"})
    save(out_dir, "planner_notes.json", clean(notes))

    if isinstance(courses, list):
        for course in courses[:15]:  # cap at 15 courses
            cid = course.get("id")
            if not cid:
                continue
            name = course.get("name", cid)
            print(f"  Course {cid}: {str(name)[:40]}")

            assignments = fetch(f"/courses/{cid}/assignments",
                                {"bucket": "upcoming", "per_page": "30"})
            save(out_dir, f"course_{cid}_assignments.json", clean(assignments))

            announcements = fetch(f"/courses/{cid}/discussion_topics",
                                  {"only_announcements": "true", "per_page": "10"})
            save(out_dir, f"course_{cid}_announcements.json", clean(announcements))

            modules = fetch(f"/courses/{cid}/modules", {"per_page": "20"})
            save(out_dir, f"course_{cid}_modules.json", clean(modules))

            enrollments = fetch(f"/courses/{cid}/enrollments",
                                {"user_id": "self", "per_page": "5"})
            save(out_dir, f"course_{cid}_grades.json", clean(enrollments))

            files = fetch(f"/courses/{cid}/files",
                          {"sort": "updated_at", "order": "desc", "per_page": "20"})
            save(out_dir, f"course_{cid}_files.json", clean(files))

            groups = fetch(f"/courses/{cid}/assignment_groups",
                           {"include[]": "assignments", "per_page": "20"})
            save(out_dir, f"course_{cid}_assignment_groups.json", clean(groups))

            syllabus = fetch(f"/courses/{cid}", {"include[]": "syllabus_body"})
            save(out_dir, f"course_{cid}_syllabus.json",
                 clean(syllabus if isinstance(syllabus, dict) else {}))

    print(f"\nDone. Data written to {out_dir}/")


if __name__ == "__main__":
    main()
