# canvas-sdk v2.0.0 Breaking Changes

## Summary

v2.0.0 is a clean-room rewrite of the canvas-sdk entity layer. The ~14,400 lines of code
ported from [canvasapi v3.6.0](https://github.com/ucfopen/canvasapi) (MIT) have been deleted
and replaced with ~550 lines of original Python (GPL-3.0). Three runtime dependencies
(`requests`, `arrow`, `pytz`) are dropped. The public interface is narrowed to exactly the
12 endpoints and 7 data shapes the agent and Chrome host actually use.

## Removed

### Classes removed

| Class | v1 source | Reason |
|---|---|---|
| `Canvas` | `canvas.py` (1310 lines) | Replaced by `CanvasClient` |
| `Requester` | `requester.py` (221 lines) | Replaced by stdlib `urllib` in `CanvasClient` |
| `CanvasObject` | `canvas_object.py` (52 lines) | Replaced by `@dataclass` per entity |
| `PaginatedList` | `paginated_list.py` (173 lines) | Replaced by internal generator in `CanvasClient` |
| `CurrentUser` | `current_user.py` | Replaced by `User` dataclass |
| `Account` and all 50+ entity classes | various | Zero external call sites; deleted entirely |

All entity files in the following list were removed:
`account.py`, `account_calendar.py`, `appointment_group.py`, `assignment.py`,
`authentication_event.py`, `authentication_provider.py`, `avatar.py`, `blueprint.py`,
`bookmark.py`, `calendar_event.py`, `collaboration.py`, `comm_message.py`,
`communication_channel.py`, `content_export.py`, `content_migration.py`, `conversation.py`,
`course.py`, `course_epub_export.py`, `course_event.py`, `current_user.py`,
`custom_gradebook_columns.py`, `discussion_topic.py`, `enrollment.py`, `enrollment_term.py`,
`eportfolio.py`, `external_feed.py`, `external_tool.py`, `favorite.py`, `feature.py`,
`file.py`, `folder.py`, `gradebook_history.py`, `grade_change_log.py`, `grading_period.py`,
`grading_standard.py`, `group.py`, `jwt.py`, `license.py`, `login.py`, `lti_resource_link.py`,
`module.py`, `new_quiz.py`, `notification_preference.py`, `outcome.py`, `outcome_import.py`,
`page.py`, `page_view.py`, `paginated_list.py`, `pairing_code.py`, `peer_review.py`,
`planner.py`, `poll.py`, `poll_choice.py`, `poll_session.py`, `poll_submission.py`,
`progress.py`, `quiz.py`, `quiz_group.py`, `requester.py`, `rubric.py`, `scope.py`,
`searchresult.py`, `section.py`, `sis_import.py`, `submission.py`, `tab.py`, `todo.py`,
`upload.py`, `usage_rights.py`, `user.py`, `util.py`

### Dependencies removed

| Package | v1 role | v2 |
|---|---|---|
| `requests>=2.20` | `Requester._session` | Removed — stdlib `urllib` used instead |
| `arrow>=1.0` | `CanvasObject.set_attributes` datetime parse | Removed — datetimes stored as raw strings |
| `pytz>=2019.1` | `CanvasObject.set_attributes` tz conversion | Removed |
| `httpx>=0.24` | Already required (Gemma4Backend) | Retained for agent layer |

## New Surface

### `CanvasClient(base_url, access_token, *, timeout=30.0)`

12 read-only GET methods:

```python
client.get_current_user() -> User
client.get_courses(*, enrollment_state=None, include=None, per_page=100) -> list[Course]
client.get_course(course_id, *, include=None) -> Course
client.get_assignments(course_id, *, bucket=None, include=None, per_page=100) -> list[Assignment]
client.get_enrollments(course_id, *, user_id=None, include=None) -> list[Enrollment]
client.get_discussion_topics(course_id, *, only_announcements=False) -> list[DiscussionTopic]
client.get_modules(course_id) -> list[dict]
client.get_files(course_id) -> list[dict]
client.get_announcements(*, context_codes, start_date=None) -> list[DiscussionTopic]
client.get_todo_items() -> list[Todo]
client.get_planner_notes() -> list[PlannerNote]
client.get_upcoming_events() -> list[dict]
```

### 7 dataclasses

`Course`, `Assignment`, `DiscussionTopic`, `Todo`, `PlannerNote`, `Enrollment`, `User`.

Each has a `from_api(cls, data)` classmethod and an `extra_fields: dict` attribute that
stores any Canvas API fields not explicitly declared on the dataclass.

### 8 exception classes

All inherit from `CanvasException`:
`InvalidAccessToken`, `Forbidden`, `ResourceNotFound`, `Conflict`, `UnprocessableEntity`,
`RateLimitExceeded`, `CanvasServerError`.

## Migration Guide

### Instantiation

```python
# v1
from canvas_sdk import Canvas
c = Canvas("https://canvas.vt.edu", token)

# v2
from canvas_sdk import CanvasClient
c = CanvasClient("https://canvas.vt.edu", token)
```

### Fetching courses

```python
# v1 — returned CanvasObject instances; attribute access via getattr
courses = c.get_courses(enrollment_state="active", per_page=100)
for course in courses:
    print(getattr(course, "name", ""))

# v2 — returns Course dataclasses; direct attribute access
courses = c.get_courses(enrollment_state="active", per_page=100)
for course in courses:
    print(course.name)
```

### Fetching assignments (was on Course, now on client)

```python
# v1
course = c.get_course(course_id)
assignments = course.get_assignments(bucket="upcoming", include=["submission"], per_page=100)

# v2
assignments = c.get_assignments(course_id, bucket="upcoming", include=["submission"], per_page=100)
```

### Announcements (now keyword-only)

```python
# v1 — positional first arg accepted
c.get_announcements(context_codes, start_date=since)

# v2 — keyword-only
c.get_announcements(context_codes=context_codes, start_date=since)
```

### Fields not declared on dataclasses

Canvas API fields that are included via `include[]` parameters (e.g., `teachers`, `term`,
`total_students`, `syllabus_body` beyond the declared field, `submission` on assignments)
are stored in `obj.extra_fields`:

```python
# v1
teachers = getattr(course, "teachers", [])

# v2
teachers = course.extra_fields.get("teachers", [])

# Exception: syllabus_body is a declared field on Course
raw = course.syllabus_body or ""
```

## License Note

The v1 entity layer was a port of canvasapi v3.6.0 (MIT licensed).
The v2 entity layer (`client.py`, `entities.py`, `exceptions.py`) is original code
written from the Canvas API public documentation and is licensed under GPL-3.0,
consistent with the rest of this repository.
