"""
Chrome Native Messaging host for Canvas Tracker.

Chrome pipes JSON messages through stdin/stdout using a 4-byte little-endian
length prefix per message. This process reads those messages, calls the Python
SDK, and writes back JSON responses in the same format.

Usage (Chrome registers this via the host manifest):
  python -m canvas_sdk.host
"""

import json
import struct
import sys
from typing import Any

from canvas_sdk.canvas import Canvas


# ── Serialization ─────────────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """Recursively convert CanvasObject / PaginatedList to plain dicts/lists."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    # CanvasObject — attrs are instance vars; skip private + _date variants
    if hasattr(obj, '__dict__'):
        out = {}
        for k, v in vars(obj).items():
            if k.startswith('_') or k.endswith('_date'):
                continue
            out[k] = _serialize(v)
        return out
    return str(obj)


def _drain(paginated, limit: int = 100) -> list:
    """Pull up to `limit` items from a PaginatedList and serialize."""
    results = []
    for item in paginated:
        results.append(_serialize(item))
        if len(results) >= limit:
            break
    return results


# ── Message I/O (Chrome native messaging wire format) ─────────────────────────

def _read() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    length = struct.unpack('<I', raw)[0]
    data = sys.stdin.buffer.read(length)
    return json.loads(data.decode('utf-8'))


def _write(msg: dict) -> None:
    encoded = json.dumps(msg, default=str).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('<I', len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


# ── Dispatch ──────────────────────────────────────────────────────────────────

def _handle(msg: dict) -> dict:
    method = msg.get('method')
    token = msg.get('token')
    base_url = msg.get('baseUrl', 'https://canvas.vt.edu')
    params = msg.get('params', {})

    if not token:
        return {'ok': False, 'error': 'No token'}

    canvas = Canvas(base_url, token)

    if method == 'getUser':
        user = canvas.get_current_user()
        return {'ok': True, 'data': _serialize(user)}

    if method == 'validateToken':
        user = canvas.get_current_user()
        return {'ok': True, 'user': _serialize(user)}

    if method == 'getCourses':
        courses = canvas.get_courses(
            enrollment_state='active',
            include=['teachers'],
            per_page=100,
        )
        return {'ok': True, 'data': _drain(courses)}

    if method == 'getUpcomingAssignments':
        events = canvas.get_upcoming_events(per_page=50)
        return {'ok': True, 'data': _drain(events)}

    if method == 'getTodo':
        items = canvas.get_todo_items()
        return {'ok': True, 'data': _drain(items)}

    if method == 'getPlannerNotes':
        notes = canvas.get_planner_notes()
        return {'ok': True, 'data': _drain(notes)}

    course_id = params.get('courseId')
    if not course_id and method.startswith('getCourse'):
        return {'ok': False, 'error': 'courseId required'}

    if method == 'getCourseAssignments':
        course = canvas.get_course(course_id)
        assignments = course.get_assignments(
            include=['submission'],
            per_page=50,
        )
        return {'ok': True, 'data': _drain(assignments)}

    if method == 'getCourseGrades':
        # Returns enrollment with current_score, final_score, computed_current_grade
        course = canvas.get_course(course_id)
        enrollments = course.get_enrollments(
            user_id='self',
            include=['current_points', 'final_grade'],
        )
        return {'ok': True, 'data': _drain(enrollments)}

    if method == 'getCourseAnnouncements':
        course = canvas.get_course(course_id)
        topics = course.get_discussion_topics(only_announcements=True, per_page=25)
        return {'ok': True, 'data': _drain(topics)}

    if method == 'getCourseModules':
        course = canvas.get_course(course_id)
        modules = course.get_modules(per_page=100)
        return {'ok': True, 'data': _drain(modules)}

    if method == 'getCourseFiles':
        course = canvas.get_course(course_id)
        files = course.get_files(per_page=50)
        return {'ok': True, 'data': _drain(files)}

    return {'ok': False, 'error': f'Unknown method: {method}'}


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    while True:
        try:
            msg = _read()
            if msg is None:
                break
            result = _handle(msg)
        except Exception as exc:  # noqa: BLE001
            result = {'ok': False, 'error': str(exc)}
        _write(result)


if __name__ == '__main__':
    main()
