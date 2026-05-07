# SPDX-License-Identifier: GPL-3.0-or-later
from datetime import UTC, datetime

import pytest


@pytest.fixture
def fixed_now():
    return datetime(2026, 5, 10, 9, 0, 0, tzinfo=UTC)


@pytest.fixture
def exam_iso():
    return "2026-05-22T14:00:00Z"
