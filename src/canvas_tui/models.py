"""Data models for Canvas TUI — typed dataclasses replacing raw dicts.

New layout (v2): one class per file under models/
  - models/item.py   — CanvasItem
  - models/course.py — CourseInfo
  - models/modal.py  — ModalContext
  - models/__init__.py — re-exports

The top-level models.py remains as a compatibility shim.
"""
from __future__ import annotations

# Re-export from new package layout
from .item import CanvasItem
from .course import CourseInfo
from .modal import ModalContext

__all__ = ["CanvasItem", "CourseInfo", "ModalContext"]