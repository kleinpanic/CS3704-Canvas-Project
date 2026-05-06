# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import dataclasses
from typing import Optional


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
    id: Optional[int] = None
    name: Optional[str] = None
    course_code: Optional[str] = None
    workflow_state: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    enrollment_term_id: Optional[int] = None
    time_zone: Optional[str] = None
    default_view: Optional[str] = None
    syllabus_body: Optional[str] = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> "Course":
        return _from_api(cls, data)


@dataclasses.dataclass
class Assignment:
    id: Optional[int] = None
    course_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    due_at: Optional[str] = None
    unlock_at: Optional[str] = None
    lock_at: Optional[str] = None
    points_possible: Optional[float] = None
    submission_types: Optional[list] = None
    workflow_state: Optional[str] = None
    html_url: Optional[str] = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> "Assignment":
        return _from_api(cls, data)


@dataclasses.dataclass
class DiscussionTopic:
    id: Optional[int] = None
    course_id: Optional[int] = None
    title: Optional[str] = None
    message: Optional[str] = None
    html_url: Optional[str] = None
    posted_at: Optional[str] = None
    delayed_post_at: Optional[str] = None
    last_reply_at: Optional[str] = None
    discussion_type: Optional[str] = None
    read_state: Optional[str] = None
    unread_count: Optional[int] = None
    workflow_state: Optional[str] = None
    is_announcement: Optional[bool] = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> "DiscussionTopic":
        return _from_api(cls, data)


@dataclasses.dataclass
class Todo:
    type: Optional[str] = None
    assignment: Optional[dict] = None
    ignore: Optional[str] = None
    ignore_permanently: Optional[str] = None
    html_url: Optional[str] = None
    needs_grading_count: Optional[int] = None
    context_type: Optional[str] = None
    course_id: Optional[int] = None
    group_id: Optional[int] = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> "Todo":
        return _from_api(cls, data)


@dataclasses.dataclass
class PlannerNote:
    id: Optional[int] = None
    title: Optional[str] = None
    details: Optional[str] = None
    user_id: Optional[int] = None
    course_id: Optional[int] = None
    workflow_state: Optional[str] = None
    todo_date: Optional[str] = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> "PlannerNote":
        return _from_api(cls, data)


@dataclasses.dataclass
class Enrollment:
    id: Optional[int] = None
    course_id: Optional[int] = None
    course_section_id: Optional[int] = None
    user_id: Optional[int] = None
    type: Optional[str] = None
    role: Optional[str] = None
    enrollment_state: Optional[str] = None
    grades: Optional[dict] = None
    html_url: Optional[str] = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> "Enrollment":
        return _from_api(cls, data)


@dataclasses.dataclass
class User:
    id: Optional[int] = None
    name: Optional[str] = None
    sortable_name: Optional[str] = None
    short_name: Optional[str] = None
    login_id: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    time_zone: Optional[str] = None
    locale: Optional[str] = None
    extra_fields: dict = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict) -> "User":
        return _from_api(cls, data)
