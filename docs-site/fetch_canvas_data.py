#!/usr/bin/env python3
"""
CI script: pre-fetch Canvas API data and save as static JSON for the live demo.

Usage:
  CANVAS_TOKEN=<token> CANVAS_BASE_URL=https://canvas.school.edu \
      python3 docs-site/fetch_canvas_data.py --out site/data
  python3 docs-site/fetch_canvas_data.py --mock --out site/data   # fake data, no token needed
  python3 docs-site/fetch_canvas_data.py --self-test              # regex + Piiranha mock self-test

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
from datetime import datetime, timedelta
from pathlib import Path

CANVAS_BASE = os.environ.get("CANVAS_BASE_URL", "https://canvas.example.edu").rstrip("/") + "/api/v1"
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


def generate_mock_data(out_dir: Path):
    now = datetime.now()
    fmt = "%Y-%m-%dT%H:%M:%SZ"

    def due(days): return (now + timedelta(days=days)).strftime(fmt)

    courses = [
        {"id": 131071, "name": "CS 3704: Software Design and Engineering",
         "course_code": "CS 3704", "enrollment_state": "active",
         "teachers": [{"display_name": "Emily Williams"}]},
        {"id": 131072, "name": "CS 3744: Introduction to Human-Computer Interaction",
         "course_code": "CS 3744", "enrollment_state": "active",
         "teachers": [{"display_name": "David Chen"}]},
        {"id": 131073, "name": "MATH 2224: Multivariable Calculus",
         "course_code": "MATH 2224", "enrollment_state": "active",
         "teachers": [{"display_name": "Maria Rodriguez"}]},
    ]

    assignments_by_course = {
        131071: [
            {"id": 901, "name": "Project 3 — API Integration", "course_id": 131071,
             "due_at": due(5), "points_possible": 100, "submission_types": ["online_upload"]},
            {"id": 902, "name": "Homework 8 — Design Patterns", "course_id": 131071,
             "due_at": due(2), "points_possible": 20, "submission_types": ["online_upload"]},
            {"id": 903, "name": "Quiz 4 — SOLID Principles", "course_id": 131071,
             "due_at": due(9), "points_possible": 15, "submission_types": ["online_quiz"]},
        ],
        131072: [
            {"id": 904, "name": "Usability Study Report", "course_id": 131072,
             "due_at": due(4), "points_possible": 75, "submission_types": ["online_upload"]},
            {"id": 905, "name": "Prototype Critique Peer Review", "course_id": 131072,
             "due_at": due(7), "points_possible": 25, "submission_types": ["online_upload"]},
        ],
        131073: [
            {"id": 906, "name": "Problem Set 11 — Partial Derivatives", "course_id": 131073,
             "due_at": due(1), "points_possible": 30, "submission_types": ["online_upload"]},
            {"id": 907, "name": "Midterm Exam 2", "course_id": 131073,
             "due_at": due(12), "points_possible": 100, "submission_types": ["on_paper"]},
        ],
    }

    upcoming = [
        {"id": f"a_{a['id']}", "type": "Assignment",
         "title": a["name"], "course_id": a["course_id"],
         "assignment": {"due_at": a["due_at"], "points_possible": a["points_possible"]}}
        for cid, asgns in assignments_by_course.items() for a in asgns
    ]

    todo = [
        {"type": "submitting", "assignment": a, "context_name": next(
            c["name"] for c in courses if c["id"] == a["course_id"])}
        for cid, asgns in assignments_by_course.items()
        for a in asgns[:2]
    ]

    announcements_by_course = {
        131071: [
            {"id": 801, "title": "Office Hours Changed This Week",
             "message": "Office hours moved to Thursday 3-5 PM due to faculty meeting.",
             "posted_at": (now - timedelta(days=2)).strftime(fmt)},
            {"id": 802, "title": "Project 3 Clarification",
             "message": "You may use any REST API for Project 3, not just Canvas. See Piazza for examples.",
             "posted_at": (now - timedelta(days=1)).strftime(fmt)},
        ],
        131072: [
            {"id": 803, "title": "Guest Speaker Next Tuesday",
             "message": "We will have a UX designer from Figma joining us virtually on Tuesday.",
             "posted_at": (now - timedelta(days=3)).strftime(fmt)},
        ],
        131073: [
            {"id": 804, "title": "Midterm 2 Coverage",
             "message": "Midterm 2 covers Chapters 11–14: partial derivatives, multiple integrals, and line integrals.",
             "posted_at": (now - timedelta(days=1)).strftime(fmt)},
        ],
    }

    modules_by_course = {
        131071: [
            {"id": 501, "name": "Week 12 — API Design Patterns", "position": 12,
             "completed_at": None, "state": "started"},
            {"id": 502, "name": "Week 13 — Testing & CI/CD", "position": 13,
             "completed_at": None, "state": "unlocked"},
        ],
        131072: [
            {"id": 503, "name": "Module 5 — User Research Methods", "position": 5,
             "completed_at": (now - timedelta(days=5)).strftime(fmt), "state": "completed"},
            {"id": 504, "name": "Module 6 — Prototyping & Wireframing", "position": 6,
             "completed_at": None, "state": "started"},
        ],
        131073: [
            {"id": 505, "name": "Chapter 11 — Partial Derivatives", "position": 11,
             "completed_at": (now - timedelta(days=7)).strftime(fmt), "state": "completed"},
            {"id": 506, "name": "Chapter 12 — Multiple Integrals", "position": 12,
             "completed_at": None, "state": "started"},
        ],
    }

    grades_by_course = {
        131071: [{"type": "StudentEnrollment", "grades": {"current_score": 87.5, "current_grade": "B+"}}],
        131072: [{"type": "StudentEnrollment", "grades": {"current_score": 91.0, "current_grade": "A-"}}],
        131073: [{"type": "StudentEnrollment", "grades": {"current_score": 78.3, "current_grade": "C+"}}],
    }

    files_by_course = {
        131071: [
            {"id": 701, "filename": "lecture_12_api_design.pdf", "display_name": "Lecture 12 Slides",
             "size": 2048000, "updated_at": (now - timedelta(days=3)).strftime(fmt)},
            {"id": 702, "filename": "project3_requirements.pdf", "display_name": "Project 3 Requirements",
             "size": 512000, "updated_at": (now - timedelta(days=5)).strftime(fmt)},
        ],
        131072: [
            {"id": 703, "filename": "heuristic_eval_template.docx", "display_name": "Heuristic Evaluation Template",
             "size": 128000, "updated_at": (now - timedelta(days=6)).strftime(fmt)},
        ],
        131073: [
            {"id": 704, "filename": "ch12_multiple_integrals.pdf", "display_name": "Chapter 12 Notes",
             "size": 1024000, "updated_at": (now - timedelta(days=4)).strftime(fmt)},
        ],
    }

    assignment_groups_by_course = {
        131071: [
            {"id": 301, "name": "Homework", "group_weight": 20,
             "assignments": assignments_by_course[131071][:2]},
            {"id": 302, "name": "Projects", "group_weight": 50,
             "assignments": [assignments_by_course[131071][0]]},
        ],
        131072: [
            {"id": 303, "name": "Reports", "group_weight": 40,
             "assignments": assignments_by_course[131072]},
        ],
        131073: [
            {"id": 304, "name": "Problem Sets", "group_weight": 30,
             "assignments": [assignments_by_course[131073][0]]},
            {"id": 305, "name": "Exams", "group_weight": 60,
             "assignments": [assignments_by_course[131073][1]]},
        ],
    }

    syllabus_by_course = {
        131071: {"id": 131071, "name": "CS 3704: Software Design and Engineering",
                 "syllabus_body": "<p>This course covers intermediate software design principles...</p>"},
        131072: {"id": 131072, "name": "CS 3744: Introduction to Human-Computer Interaction",
                 "syllabus_body": "<p>Students learn HCI fundamentals: user research, prototyping...</p>"},
        131073: {"id": 131073, "name": "MATH 2224: Multivariable Calculus",
                 "syllabus_body": "<p>Topics: partial derivatives, multiple integrals, line integrals...</p>"},
    }

    planner_notes = [
        {"id": 201, "title": "Review lecture notes before Midterm 2", "todo_date": due(10)},
        {"id": 202, "title": "Start Project 3 API integration early", "todo_date": due(3)},
    ]

    dashboard_cards = [
        {"id": c["id"], "shortName": c["course_code"], "originalName": c["name"],
         "courseCode": c["course_code"], "enrollmentState": "active",
         "color": "#1a73e8" if i == 0 else "#34a853" if i == 1 else "#ea4335"}
        for i, c in enumerate(courses)
    ]

    rmp_data = {
        "Emily Williams": {"rating": 4.2, "difficulty": 3.1, "numRatings": 47},
        "Williams": {"rating": 4.2, "difficulty": 3.1, "numRatings": 47},
        "David Chen": {"rating": 3.9, "difficulty": 2.8, "numRatings": 31},
        "Chen": {"rating": 3.9, "difficulty": 2.8, "numRatings": 31},
        "Maria Rodriguez": {"rating": 4.5, "difficulty": 3.7, "numRatings": 62},
        "Rodriguez": {"rating": 4.5, "difficulty": 3.7, "numRatings": 62},
    }

    def w(filename, data):
        path = out_dir / filename
        with open(path, "w") as f:
            json.dump({"ok": True, "data": data}, f)
        print(f"  wrote {path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    w("courses.json", courses)
    w("upcoming.json", upcoming)
    w("todo.json", todo)
    w("planner_notes.json", planner_notes)
    w("dashboard_cards.json", dashboard_cards)
    w("rmp.json", rmp_data)

    for cid in [131071, 131072, 131073]:
        w(f"course_{cid}_assignments.json", assignments_by_course[cid])
        w(f"course_{cid}_announcements.json", announcements_by_course[cid])
        w(f"course_{cid}_modules.json", modules_by_course[cid])
        w(f"course_{cid}_grades.json", grades_by_course[cid])
        w(f"course_{cid}_files.json", files_by_course[cid])
        w(f"course_{cid}_assignment_groups.json", assignment_groups_by_course[cid])
        w(f"course_{cid}_syllabus.json", syllabus_by_course[cid])

    print(f"\nMock data written to {out_dir}/ (3 courses, dates relative to build time)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data", help="Output directory")
    ap.add_argument("--self-test", action="store_true",
                    help="Run regex self-test and exit (no network calls)")
    ap.add_argument("--mock", action="store_true",
                    help="Generate realistic fake data without a Canvas token")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if args.mock:
        generate_mock_data(Path(args.out))
        return

    if not os.environ.get("CANVAS_BASE_URL"):
        print("ERROR: CANVAS_BASE_URL must be set (e.g. https://canvas.yourschool.edu)", file=sys.stderr)
        sys.exit(1)

    if not TOKEN:
        print("ERROR: CANVAS_TOKEN or CANVAS_API_TOKEN env var not set", file=sys.stderr)
        sys.exit(1)

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
