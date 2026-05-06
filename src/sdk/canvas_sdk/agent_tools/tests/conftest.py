# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from datetime import datetime, timezone


@pytest.fixture
def fixed_now():
    return datetime(2026, 5, 10, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def exam_iso():
    return "2026-05-22T14:00:00Z"
