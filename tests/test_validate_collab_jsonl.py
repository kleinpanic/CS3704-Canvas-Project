# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/validate_collab_jsonl.py — 6 cases covering all failure modes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run(
    tmp_path: Path,
    lines: list[str],
    extra_args: list[str] | None = None,
    env_overrides: dict | None = None,
) -> subprocess.CompletedProcess:
    jsonl = tmp_path / "test.jsonl"
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [sys.executable, "tools/validate_collab_jsonl.py"] + (extra_args or []) + [str(jsonl)]
    env = os.environ.copy()
    if env_overrides is not None:
        for k, v in env_overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env=env,
    )


VALID_RECORD = {
    "type": "course_snapshot",
    "contributor_id": "testuser42",
    "collected_at": "2026-05-06T00:00:00Z",
    "course_code": "@COURSE1/3704 S26",
}


def test_malformed_json(tmp_path):
    """Case 1: malformed JSON line exits 1."""
    result = _run(tmp_path, ["{not valid json"])
    assert result.returncode == 1
    assert "invalid JSON" in result.stdout


def test_missing_required_field(tmp_path):
    """Case 2: missing required field exits 1."""
    record = {k: v for k, v in VALID_RECORD.items() if k != "contributor_id"}
    result = _run(tmp_path, [json.dumps(record)])
    assert result.returncode == 1
    assert "missing required field" in result.stdout


def test_course_name_present(tmp_path):
    """Case 3: forbidden course_name field exits 1."""
    record = {**VALID_RECORD, "course_name": "Data Structures"}
    result = _run(tmp_path, [json.dumps(record)])
    assert result.returncode == 1
    assert "course_name" in result.stdout


def test_non_anonymized_course_code(tmp_path):
    """Case 4: bare course_code (e.g. CS_3114_202601) exits 1."""
    record = {**VALID_RECORD, "course_code": "CS_3114_202601"}
    result = _run(tmp_path, [json.dumps(record)])
    assert result.returncode == 1
    assert "non-anonymized course_code" in result.stdout


def test_pii_in_description_no_token(tmp_path):
    """Case 5: email in a SCRUB_KEYS field without HF_TOKEN hits regex, exits 1."""
    record = {**VALID_RECORD, "description": "Contact alice@example.com for info"}
    result = _run(
        tmp_path,
        [json.dumps(record)],
        extra_args=["--pii"],
        env_overrides={"HF_TOKEN": None},
    )
    assert result.returncode == 1
    assert "PII detected" in result.stdout


def test_valid_record_passes(tmp_path):
    """Case 6: clean record with anonymized course_code exits 0."""
    result = _run(tmp_path, [json.dumps(VALID_RECORD)])
    assert result.returncode == 0
    assert "OK:" in result.stdout
