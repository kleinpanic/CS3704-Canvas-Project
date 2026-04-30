"""UI state types — modals, navigation, and screen context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModalContext:
    """Context for tracking pending modal screens.

    Uses UUID instead of id(screen) for stable cross-references.
    """

    modal_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: str = ""
    ctx: dict[str, Any] = field(default_factory=dict)
