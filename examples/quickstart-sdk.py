#!/usr/bin/env python3
# quickstart-sdk.py — minimal CanvasClient example
#
# Requirements:
#   pip install canvas-sdk
#
# Required env vars:
#   CANVAS_BASE_URL  — your institution's Canvas URL
#                      e.g. https://your-institution.instructure.com
#   CANVAS_TOKEN     — your Canvas API access token
#                      Canvas -> Account -> Settings -> New Access Token
#
# WARNING: Never commit output of this script; it may contain course names or grades.
# Docs: docs/QUICKSTART.md | examples/quickstart-extension.md
import os
import sys

missing = [v for v in ("CANVAS_BASE_URL", "CANVAS_TOKEN") if not os.environ.get(v)]
if missing:
    print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
    print("  export CANVAS_BASE_URL='https://your-institution.instructure.com'")
    print("  export CANVAS_TOKEN='your_token'")
    sys.exit(1)

from canvas_sdk import CanvasClient

client = CanvasClient(
    base_url=os.environ["CANVAS_BASE_URL"],
    access_token=os.environ["CANVAS_TOKEN"],
)

# --- Call 1: current user ---
user = client.get_current_user()
print(f"\nLogged in as: {user.name} (id={user.id})")

# --- Call 2: course list ---
courses = client.get_courses()
if not courses:
    print("No active courses found.")
    sys.exit(0)

print(f"\nActive courses ({len(courses)} total):")
for course in courses[:5]:
    print(f"  [{course.id}] {course.name}")
if len(courses) > 5:
    print(f"  ... and {len(courses) - 5} more")

# --- Call 3: assignments for the first course ---
first = courses[0]
assignments = client.get_assignments(course_id=first.id)
print(f"\nAssignments in '{first.name}' ({len(assignments)} total):")
for a in assignments[:5]:
    due = a.due_at or "no due date"
    print(f"  [{a.id}] {a.name}  — due: {due}")
if len(assignments) > 5:
    print(f"  ... and {len(assignments) - 5} more")

print("\nDone. See docs/QUICKSTART.md for next steps.")
