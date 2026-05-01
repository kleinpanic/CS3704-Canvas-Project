"""Data models for Rate My Professor integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ProfessorRating:
    """A single professor's rating snapshot from RateMyProfessors."""

    rmp_id: int
    first_name: str
    last_name: str
    department: str
    rating: float  # 1.0 - 5.0
    difficulty: float  # 1.0 - 5.0
    num_ratings: int
    would_take_again_percent: Optional[float] = None
    url: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_rating(self) -> str:
        return f"{self.rating:.1f}" if self.rating else "N/A"

    @property
    def display_difficulty(self) -> str:
        return f"{self.difficulty:.1f}" if self.difficulty else "N/A"

    @property
    def display_would_take_again(self) -> str:
        if self.would_take_again_percent is None:
            return "N/A"
        return f"{self.would_take_again_percent:.0f}%"


@dataclass
class MatchResult:
    """Result of matching a Canvas instructor to an RMP professor."""

    canvas_name: str
    matched: Optional[ProfessorRating] = None
    confidence: str = "none"  # exact, fuzzy, none
    candidates: list[ProfessorRating] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_matched(self) -> bool:
        return self.matched is not None

    @property
    def display_confidence(self) -> str:
        return {
            "exact": "✓",
            "fuzzy": "~",
            "none": "✗",
        }.get(self.confidence, "?")
