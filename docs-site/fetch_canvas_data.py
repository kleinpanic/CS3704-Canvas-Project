#!/usr/bin/env python3
"""
CI script: pre-fetch Canvas API data and save as static JSON for the live demo.

Usage:
  CANVAS_TOKEN=<token> python3 docs-site/fetch_canvas_data.py --out site/data

Output files (all in --out dir):
  courses.json
  upcoming.json
  todo.json
  planner_notes.json
  course_<id>_assignments.json
  course_<id>_announcements.json
  course_<id>_modules.json
  course_<id>_grades.json
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

CANVAS_BASE = "https://canvas.vt.edu/api/v1"
TOKEN = os.environ.get("CANVAS_TOKEN") or os.environ.get("CANVAS_API_TOKEN", "")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data", help="Output directory")
    args = ap.parse_args()

    if not TOKEN:
        print("ERROR: CANVAS_TOKEN or CANVAS_API_TOKEN env var not set", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching courses...")
    courses = fetch("/courses", {"enrollment_state": "active", "per_page": "50"})
    save(out_dir, "courses.json", courses)

    print("Fetching upcoming assignments...")
    upcoming = fetch("/users/self/upcoming_events", {"per_page": "50"})
    if not upcoming:
        upcoming = fetch("/users/self/calendar_events", {"type": "assignment", "per_page": "50"})
    save(out_dir, "upcoming.json", upcoming)

    print("Fetching todo...")
    todo = fetch("/users/self/todo", {"per_page": "50"})
    save(out_dir, "todo.json", todo)

    print("Fetching dashboard cards...")
    cards = fetch("/dashboard/dashboard_cards")
    save(out_dir, "dashboard_cards.json", cards if isinstance(cards, list) else [])

    print("Fetching planner notes...")
    notes = fetch("/planner/items", {"per_page": "50"})
    save(out_dir, "planner_notes.json", notes)

    if isinstance(courses, list):
        for course in courses[:15]:  # cap at 15 courses
            cid = course.get("id")
            if not cid:
                continue
            name = course.get("name", cid)
            print(f"  Course {cid}: {name[:40]}")

            assignments = fetch(f"/courses/{cid}/assignments",
                                {"bucket": "upcoming", "per_page": "30"})
            save(out_dir, f"course_{cid}_assignments.json", assignments)

            announcements = fetch(f"/courses/{cid}/discussion_topics",
                                  {"only_announcements": "true", "per_page": "10"})
            save(out_dir, f"course_{cid}_announcements.json", announcements)

            modules = fetch(f"/courses/{cid}/modules", {"per_page": "20"})
            save(out_dir, f"course_{cid}_modules.json", modules)

            enrollments = fetch(f"/courses/{cid}/enrollments",
                                {"user_id": "self", "per_page": "5"})
            save(out_dir, f"course_{cid}_grades.json", enrollments)

            files = fetch(f"/courses/{cid}/files",
                          {"sort": "updated_at", "order": "desc", "per_page": "20"})
            save(out_dir, f"course_{cid}_files.json", files)

            groups = fetch(f"/courses/{cid}/assignment_groups",
                           {"include[]": "assignments", "per_page": "20"})
            save(out_dir, f"course_{cid}_assignment_groups.json", groups)

            syllabus = fetch(f"/courses/{cid}", {"include[]": "syllabus_body"})
            save(out_dir, f"course_{cid}_syllabus.json",
                 syllabus if isinstance(syllabus, dict) else {})

    print(f"\nDone. Data written to {out_dir}/")


if __name__ == "__main__":
    main()
