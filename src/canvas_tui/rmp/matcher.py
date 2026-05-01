"""Professor matching logic.

Matches Canvas instructor names against RateMyProfessors data
using normalized name comparison and optional fuzzy matching.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .models import ProfessorRating, MatchResult

# Suffixes and titles to strip during normalization
_STRIP_SUFFIXES = {
    "jr", "sr", "ii", "iii", "iv", "v", "vi",
    "md", "phd", "esq", "dds", "dvm", "do", "ed",
}
_STRIP_TITLES = {
    "dr", "prof", "professor", "mr", "mrs", "ms", "miss",
    "instructor", "lecturer", "adjunct", "assistant", "associate",
}


def normalize_name(name: str) -> str:
    """Normalize a name for comparison.

    - lowercase
    - strip accents/diacritics
    - remove punctuation
    - remove common titles and suffixes
    - collapse whitespace
    """
    # Decompose unicode (accents) and strip combining marks
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_friendly = "".join(c for c in nfkd if not unicodedata.combining(c))

    # Lowercase
    ascii_friendly = ascii_friendly.lower()

    # Remove punctuation except spaces
    ascii_friendly = re.sub(r"[^\w\s]", "", ascii_friendly)

    # Tokenize and filter titles/suffixes
    tokens = ascii_friendly.split()
    tokens = [t for t in tokens if t not in _STRIP_TITLES and t not in _STRIP_SUFFIXES]

    return " ".join(tokens)


def parse_first_last(name: str) -> tuple[str, str]:
    """Extract (first, last) from a display name.

    Handles formats like:
    - "John Smith"
    - "Smith, John"
    - "John A. Smith"
    - "Dr. John Smith Jr."
    """
    normalized = normalize_name(name)
    if not normalized:
        return ("", "")

    # If comma-separated in the original, assume "Last, First"
    if "," in name:
        raw_parts = name.split(",", 1)
        # Take only the first token of each part for consistency with the non-comma path
        last_raw = normalize_name(raw_parts[0]).split()
        first_raw = normalize_name(raw_parts[1]).split() if len(raw_parts) > 1 else []
        first = first_raw[0] if first_raw else ""
        last = last_raw[-1] if last_raw else ""
        return (first, last)

    tokens = normalized.split()
    if len(tokens) == 1:
        return ("", tokens[0])
    return (tokens[0], tokens[-1])


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def match_professor(
    canvas_name: str,
    candidates: Sequence[ProfessorRating],
    fuzzy_threshold: int = 2,
) -> MatchResult:
    """Match a Canvas instructor name against a list of RMP professor candidates.

    Strategy:
    1. Normalize both names.
    2. Try exact match on (first, last).
    3. Try exact match on last name only, then first name fuzzy.
    4. Try fuzzy match on both.
    5. Return best candidate or no match.
    """
    result = MatchResult(canvas_name=canvas_name, candidates=list(candidates))

    if not candidates:
        result.confidence = "none"
        return result

    canvas_first, canvas_last = parse_first_last(canvas_name)

    if not canvas_last:
        result.confidence = "none"
        return result

    # Score each candidate
    scored: list[tuple[int, ProfessorRating, str]] = []

    for prof in candidates:
        prof_first, prof_last = parse_first_last(f"{prof.first_name} {prof.last_name}")

        # Exact full match
        if canvas_first == prof_first and canvas_last == prof_last:
            scored.append((0, prof, "exact"))
            continue

        # Exact last name + fuzzy first (only if both have first names)
        if canvas_last == prof_last and canvas_first and prof_first:
            dist = levenshtein_distance(canvas_first, prof_first)
            if dist <= fuzzy_threshold:
                scored.append((dist + 1, prof, "fuzzy"))
                continue

        # Last-name-only match when first name is missing: low confidence, skip unless exact last
        if canvas_last == prof_last and (not canvas_first or not prof_first):
            scored.append((fuzzy_threshold + 3, prof, "fuzzy"))
            continue

        # Fuzzy last name
        last_dist = levenshtein_distance(canvas_last, prof_last)
        if last_dist <= fuzzy_threshold:
            first_dist = levenshtein_distance(canvas_first, prof_first) if canvas_first and prof_first else 0
            total = last_dist + first_dist
            if total <= fuzzy_threshold * 2:
                scored.append((total + 2, prof, "fuzzy"))

    if not scored:
        result.confidence = "none"
        return result

    # Sort by score (lower is better), break ties by num_ratings (higher is better)
    scored.sort(key=lambda x: (x[0], -x[1].num_ratings))

    best_score, best_prof, best_conf = scored[0]

    result.matched = best_prof
    result.confidence = best_conf

    # If the best match is too far off, mark as low confidence
    if best_score > fuzzy_threshold + 2:
        result.confidence = "none"
        result.matched = None

    return result


def batch_match(
    canvas_names: Sequence[str],
    professors: Sequence[ProfessorRating],
) -> dict[str, MatchResult]:
    """Match multiple Canvas instructor names against a professor list.

    Returns a dict mapping each canvas_name to its MatchResult.
    """
    results = {}
    for name in canvas_names:
        results[name] = match_professor(name, professors)
    return results
