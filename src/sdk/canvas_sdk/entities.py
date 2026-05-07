# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import dataclasses


def _from_api(cls, data: dict):
    """
    Factory helper: split incoming dict into declared-field subset and extras,
    build the dataclass, then attach extra_fields as an instance attribute.
    """
    declared = {f.name for f in dataclasses.fields(cls) if f.name != "extra_fields"}
    known = {k: v for k, v in data.items() if k in declared}
    extras = {k: v for k, v in data.items() if k not in declared}
    instance = cls(**known)
    instance.extra_fields = extras
    return instance


@dataclasses.dataclass
class Course:
    id: int | None = None
    name: str | None = None
    course_code: str | None = None
    workflow_state: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    enrollment_term_id: int | None = None
    time_zone: str | None = None
    default_view: str | None = None
    syllabus_body: str | None = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> Course:
        return _from_api(cls, data)


@dataclasses.dataclass
class Assignment:
    id: int | None = None
    course_id: int | None = None
    name: str | None = None
    description: str | None = None
    due_at: str | None = None
    unlock_at: str | None = None
    lock_at: str | None = None
    points_possible: float | None = None
    submission_types: list | None = None
    workflow_state: str | None = None
    html_url: str | None = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> Assignment:
        return _from_api(cls, data)


@dataclasses.dataclass
class DiscussionTopic:
    id: int | None = None
    course_id: int | None = None
    title: str | None = None
    message: str | None = None
    html_url: str | None = None
    posted_at: str | None = None
    delayed_post_at: str | None = None
    last_reply_at: str | None = None
    discussion_type: str | None = None
    read_state: str | None = None
    unread_count: int | None = None
    workflow_state: str | None = None
    is_announcement: bool | None = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> DiscussionTopic:
        return _from_api(cls, data)


@dataclasses.dataclass
class Todo:
    type: str | None = None
    assignment: dict | None = None
    ignore: str | None = None
    ignore_permanently: str | None = None
    html_url: str | None = None
    needs_grading_count: int | None = None
    context_type: str | None = None
    course_id: int | None = None
    group_id: int | None = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> Todo:
        return _from_api(cls, data)


@dataclasses.dataclass
class PlannerNote:
    id: int | None = None
    title: str | None = None
    details: str | None = None
    user_id: int | None = None
    course_id: int | None = None
    workflow_state: str | None = None
    todo_date: str | None = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> PlannerNote:
        return _from_api(cls, data)


@dataclasses.dataclass
class Enrollment:
    id: int | None = None
    course_id: int | None = None
    course_section_id: int | None = None
    user_id: int | None = None
    type: str | None = None
    role: str | None = None
    enrollment_state: str | None = None
    grades: dict | None = None
    html_url: str | None = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> Enrollment:
        return _from_api(cls, data)


@dataclasses.dataclass
class User:
    id: int | None = None
    name: str | None = None
    sortable_name: str | None = None
    short_name: str | None = None
    login_id: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    time_zone: str | None = None
    locale: str | None = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> User:
        return _from_api(cls, data)
