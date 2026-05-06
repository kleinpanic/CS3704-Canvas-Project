#!/usr/bin/env python3
"""
CI script: pre-fetch Canvas API data and save as static JSON for the live demo.

Usage:
  CANVAS_TOKEN=<token> python3 docs-site/fetch_canvas_data.py --out site/data
  python3 docs-site/fetch_canvas_data.py --self-test   # regex + Piiranha mock self-test

Output files (all in --out dir):
  courses.json
  upcoming.json
  todo.json
  planner_notes.json
  course_<id>_assignments.json
  course_<id>_announcements.json
  course_<id>_modules.json
  course_<id>_grades.json

PII scrubbing: two-layer approach. When HF_TOKEN is set, strings longer than 20 chars
are first sent to iiiorg/piiranha-v1-detect-personal-information via the HF Inference
API. On any error (503 warm-up, 429 rate-limit, timeout) Piiranha is disabled for the
rest of the run and the regex fallback takes over. Without HF_TOKEN the script falls
back directly to regex.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CANVAS_BASE = (os.environ.get("CANVAS_BASE_URL") or sys.exit(
    "ERROR: CANVAS_BASE_URL must be set; was previously hardcoded to canvas.vt.edu\n"
    "  e.g. export CANVAS_BASE_URL=https://canvas.yourschool.edu"
)).rstrip("/") + "/api/v1"
TOKEN = os.environ.get("CANVAS_TOKEN") or os.environ.get("CANVAS_API_TOKEN", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# ── PII scrub ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import canvas_tui.pii as _pii_mod  # noqa: E402
from canvas_tui.pii import SCRUB_KEYS, scrub_doc, scrub_string  # noqa: E402, F401

scrub_recursive = scrub_doc  # backward-compat alias for local callers


def scrub_piiranha(text, hf_token):
    """Delegate to canvas_tui.pii._piiranha_call for backward compat."""
    return _pii_mod._piiranha_call(text, hf_token)


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


def fetch_rmp(last_name: str):
    if not last_name:
        return None
    url = f"https://www.ratemyprofessors.com/filter/teacher?institution_id=1346&query={urllib.parse.quote(last_name)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        teacher = (data.get("data") or [None])[0]
        if not teacher:
            return None
        return {
            "rating": teacher.get("avg_rating"),
            "difficulty": teacher.get("avg_difficulty"),
            "numRatings": teacher.get("num_ratings", 0),
        }
    except Exception as e:
        print(f"  RMP fetch failed for {last_name}: {e}", file=sys.stderr)
        return None


def collect_teachers(courses):
    seen = set()
    out = []
    for c in courses or []:
        for t in c.get("teachers") or []:
            name = t.get("display_name")
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


def self_test():
    import io
    from unittest.mock import patch, MagicMock

    # ── regex path ────────────────────────────────────────────────────────────
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
    print("scrub self-test (regex) PASSED")

    # ── Piiranha mock path ────────────────────────────────────────────────────
    # Simulate Piiranha returning entity spans for "Hello jane@vt.edu end"
    # start=6, end=18 covers "jane@vt.edu"
    fake_entities = [{"entity_group": "EMAIL", "score": 0.99, "word": "jane@vt.edu",
                      "start": 6, "end": 17}]
    fake_response = io.BytesIO(json.dumps(fake_entities).encode())
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_cm)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_cm.read = MagicMock(return_value=json.dumps(fake_entities).encode())

    _pii_mod._piiranha_available = True  # reset in case a prior test tripped it

    with patch("canvas_tui.pii.urllib.request.urlopen", return_value=mock_cm):
        result = scrub_piiranha("Hello jane@vt.edu end", "fake-token")

    assert result is not None, "scrub_piiranha returned None with mock"
    assert "jane@vt.edu" not in result, f"PII not redacted: {result!r}"
    assert "[EMAIL]" in result, f"Expected [EMAIL] tag: {result!r}"
    print("scrub self-test (Piiranha mock) PASSED")


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

    print("Fetching courses (with teachers for RMP lookup)...")
    courses = fetch("/courses", {
        "enrollment_state": "active",
        "per_page": "50",
        "include[]": "teachers",
    })
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

    # RMP ratings — pre-fetched at build time; chrome_shim_prod.js reads from rmp.json
    print("Fetching RateMyProfessors ratings...")
    teachers = collect_teachers(courses if isinstance(courses, list) else [])
    rmp_map = {}
    for name in teachers:
        last = name.split()[-1] if name else ""
        rating = fetch_rmp(last)
        if rating:
            rmp_map[name] = rating
            rmp_map[last] = rating  # popup looks up by last-name; index both
    save(out_dir, "rmp.json", rmp_map)

    print(f"\nDone. Data written to {out_dir}/")


if __name__ == "__main__":
    main()
