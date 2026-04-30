"""Data model types for Canvas TUI.

Re-exports all model classes for convenience.
"""
from __future__ import annotations

from .course import CourseInfo
from .item import CanvasItem
from .modal import ModalContext

__all__ = ["CanvasItem", "CourseInfo", "ModalContext"]
