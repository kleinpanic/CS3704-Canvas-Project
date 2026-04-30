"""Course data types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CourseInfo:
    """Minimal course info from the API.

    Used for the course cache and quick course lookups.
    """

    course_id: int = 0
    course_code: str = ""
    name: str = ""
