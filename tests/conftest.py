"""Shared test fixtures for Canvas TUI."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure src/ and src/sdk/ are importable
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "src"))
sys.path.insert(0, str(_repo_root / "src" / "sdk"))

# D-12: set required env vars at module level so collection-time imports of
# config_env (and any module that eagerly reads env) don't sys.exit the runner.
os.environ.setdefault("CANVAS_BASE_URL", "https://canvas.test.example")
os.environ.setdefault("CANVAS_TOKEN", "test-token-fixture")


@pytest.fixture(autouse=True, scope="session")
def _canvas_env_defaults():
    """Ensure required env vars are present for all tests (D-12)."""
    os.environ.setdefault("CANVAS_BASE_URL", "https://canvas.test.example")
    os.environ.setdefault("CANVAS_TOKEN", "test-token-fixture")


@pytest.fixture
def tmp_dir():
    """Temporary directory for test files."""
    with tempfile.TemporaryDirectory(prefix="canvas_tui_test_") as d:
        yield d


@pytest.fixture
def sample_config_env(monkeypatch, tmp_dir):
    """Set up minimal environment for Config loading."""
    monkeypatch.setenv("CANVAS_TOKEN", "test-token-12345")
    monkeypatch.setenv("CANVAS_BASE_URL", "https://canvas.example.edu")
    monkeypatch.setenv("TZ", "America/New_York")
    monkeypatch.setenv("EXPORT_DIR", tmp_dir)
    return tmp_dir


@pytest.fixture
def sample_planner_item():
    """A raw planner item as returned by the Canvas API."""
    return {
        "course_id": 12345,
        "plannable_id": 67890,
        "plannable_type": "assignment",
        "plannable": {
            "id": 67890,
            "title": "Homework 3: Data Structures",
            "due_at": "2026-02-25T23:59:00Z",
            "points_possible": 100.0,
            "created_at": "2026-02-01T10:00:00Z",
        },
        "html_url": "/courses/12345/assignments/67890",
        "submissions": {
            "submitted": False,
            "graded": False,
            "missing": False,
        },
    }


@pytest.fixture
def sample_planner_items(sample_planner_item):
    """Multiple planner items for batch tests."""
    items = [sample_planner_item]
    # Add a submitted one
    submitted = json.loads(json.dumps(sample_planner_item))
    submitted["plannable_id"] = 67891
    submitted["plannable"]["id"] = 67891
    submitted["plannable"]["title"] = "Homework 2: Algorithms"
    submitted["plannable"]["due_at"] = "2026-02-20T23:59:00Z"
    submitted["submissions"] = {"submitted": True, "graded": True, "missing": False}
    items.append(submitted)
    # Add an announcement
    ann = {
        "course_id": 12345,
        "plannable_id": 99999,
        "plannable_type": "discussion_topic",
        "plannable": {
            "id": 99999,
            "title": "Class cancelled tomorrow",
            "is_announcement": True,
            "posted_at": "2026-02-22T08:00:00Z",
        },
        "html_url": "/courses/12345/discussion_topics/99999",
        "submissions": {},
    }
    items.append(ann)
    return items


@pytest.fixture
def sample_courses():
    """Raw courses response."""
    return [
        {"id": 12345, "course_code": "CS3214", "name": "Computer Systems"},
        {"id": 12346, "course_code": "CS4104", "name": "Data & Algorithm Analysis"},
    ]


@pytest.fixture
def sample_state_path(tmp_dir):
    """Path for a temporary state file."""
    return os.path.join(tmp_dir, "state.json")
