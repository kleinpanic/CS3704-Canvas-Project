"""Structured filtering and fuzzy search for Canvas TUI items."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from .models import CanvasItem


@dataclass
class FilterQuery:
    """Parsed structured filter query.

    Supports:
      course:CS3214       — match course code/name
      type:assignment      — match plannable type
      status:graded        — match status flags
      has:points           — items with points > 0
      free text            — fuzzy match across title/course/type
    """

    course: list[str] = field(default_factory=list)
    ptype: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    has: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, raw: str) -> FilterQuery:
        """Parse a filter string into structured query."""
        q = cls()
        if not raw or not raw.strip():
            return q

        # Tokenize — preserve quoted strings
        tokens = _tokenize(raw.strip())
        for tok in tokens:
            low = tok.lower()
            if ":" in low:
                prefix, _, value = tok.partition(":")
                prefix = prefix.lower().strip()
                value = value.strip()
                if not value:
                    q.text.append(tok)
                    continue
                if prefix in ("course", "c"):
                    q.course.append(value.lower())
                elif prefix in ("type", "t"):
                    q.ptype.append(value.lower())
                elif prefix in ("status", "s"):
                    q.status.append(value.lower())
                elif prefix == "has":
                    q.has.append(value.lower())
                else:
                    q.text.append(tok)
            else:
                q.text.append(tok)
        return q

    @property
    def is_empty(self) -> bool:
        return not (self.course or self.ptype or self.status or self.has or self.text)


def _tokenize(raw: str) -> list[str]:
    """Split on whitespace, preserving quoted strings."""
    tokens: list[str] = []
    pattern = re.compile(r'"([^"]*)"|\S+')
    for m in pattern.finditer(raw):
        if m.group(1) is not None:
            tokens.append(m.group(1))
        else:
            tokens.append(m.group(0))
    return tokens


def fuzzy_score(needle: str, haystack: str) -> float:
    """Simple fuzzy match score (0.0 = no match, 1.0 = exact).

    Scores: exact substring > prefix > subsequence > 0.
    """
    needle = needle.lower()
    haystack = haystack.lower()

    if not needle:
        return 1.0

    # Exact substring
    if needle in haystack:
        # Bonus for starting at word boundary
        idx = haystack.find(needle)
        if idx == 0 or haystack[idx - 1] in " _-/":
            return 0.95
        return 0.85

    # Prefix match on any word
    words = re.split(r"[\s_\-/]+", haystack)
    for w in words:
        if w.startswith(needle):
            return 0.75

    # Subsequence match
    ni = 0
    matched = 0
    for c in haystack:
        if ni < len(needle) and c == needle[ni]:
            ni += 1
            matched += 1
    if ni == len(needle):
        return 0.3 + 0.2 * (matched / len(haystack))

    return 0.0


def filter_items(items: Sequence[CanvasItem], query: FilterQuery) -> list[int]:
    """Filter items by structured query. Returns indices of matching items."""
    if query.is_empty:
        return list(range(len(items)))

    results: list[tuple[int, float]] = []

    for i, it in enumerate(items):
        score = _match_item(it, query)
        if score > 0:
            results.append((i, score))

    # Sort by score descending, then original order
    results.sort(key=lambda x: (-x[1], x[0]))
    return [idx for idx, _ in results]


def _match_item(it: CanvasItem, q: FilterQuery) -> float:
    """Score a single item against the query. 0 = no match."""
    score = 1.0

    # Structured filters (must ALL match — AND logic)
    if q.course:
        matched = any(c in it.course_code.lower() or c in it.course_name.lower() for c in q.course)
        if not matched:
            return 0.0

    if q.ptype:
        matched = any(t in it.ptype.lower() for t in q.ptype)
        if not matched:
            return 0.0

    if q.status:
        flags_lower = [f.lower() for f in it.status_flags]
        matched = any(s in flags_lower for s in q.status)
        if not matched:
            return 0.0

    if q.has:
        for h in q.has:
            if (
                (h == "points" and (it.points is None or it.points <= 0))
                or (h == "due" and not it.due_iso)
                or (h == "url" and not it.url)
            ):
                return 0.0

    # Free text — fuzzy match across combined fields
    if q.text:
        combined = f"{it.title} {it.course_code} {it.course_name} {it.ptype}"
        text_score = 0.0
        for term in q.text:
            ts = fuzzy_score(term, combined)
            if ts <= 0:
                return 0.0
            text_score = max(text_score, ts)
        score *= text_score

    return score


def format_filter_summary(query: FilterQuery, match_count: int, total: int) -> str:
    """Format a human-readable filter summary."""
    parts: list[str] = []
    if query.course:
        parts.append(f"course:{','.join(query.course)}")
    if query.ptype:
        parts.append(f"type:{','.join(query.ptype)}")
    if query.status:
        parts.append(f"status:{','.join(query.status)}")
    if query.has:
        parts.append(f"has:{','.join(query.has)}")
    if query.text:
        parts.append(" ".join(query.text))

    filter_str = " + ".join(parts) if parts else "?"
    return f"[dim]Filter:[/dim] {filter_str} → {match_count}/{total} items"
