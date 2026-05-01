"""Tests for professor name matching."""

import pytest

from canvas_tui.rmp.matcher import (
    normalize_name,
    parse_first_last,
    match_professor,
    levenshtein_distance,
)
from canvas_tui.rmp.models import ProfessorRating


def _prof(first: str, last: str, dept: str = "CS", rating: float = 4.0, num_ratings: int = 10) -> ProfessorRating:
    return ProfessorRating(
        rmp_id=hash(f"{first}{last}") % 10000,
        first_name=first,
        last_name=last,
        department=dept,
        rating=rating,
        difficulty=3.0,
        num_ratings=num_ratings,
    )


class TestNormalizeName:
    def test_simple(self):
        assert normalize_name("John Smith") == "john smith"

    def test_with_title(self):
        assert normalize_name("Dr. John Smith") == "john smith"

    def test_with_suffix(self):
        assert normalize_name("John Smith Jr.") == "john smith"

    def test_with_middle_initial(self):
        assert normalize_name("John A. Smith") == "john a smith"

    def test_comma_format(self):
        assert normalize_name("Smith, John") == "smith john"

    def test_unicode_accents(self):
        result = normalize_name("José García")
        assert "jose" in result
        assert "garcia" in result

    def test_empty(self):
        assert normalize_name("") == ""


class TestParseFirstLast:
    def test_simple(self):
        assert parse_first_last("John Smith") == ("john", "smith")

    def test_comma_format(self):
        assert parse_first_last("Smith, John") == ("john", "smith")

    def test_single_name(self):
        assert parse_first_last("Madonna") == ("", "madonna")

    def test_with_title(self):
        assert parse_first_last("Dr. John Smith") == ("john", "smith")

    def test_with_middle(self):
        assert parse_first_last("John A. Smith") == ("john", "smith")


class TestLevenshtein:
    def test_identical(self):
        assert levenshtein_distance("hello", "hello") == 0

    def test_one_edit(self):
        assert levenshtein_distance("hello", "hallo") == 1

    def test_empty(self):
        assert levenshtein_distance("", "abc") == 3


class TestMatchProfessor:
    def test_exact_match(self):
        candidates = [_prof("John", "Smith")]
        result = match_professor("John Smith", candidates)
        assert result.is_matched
        assert result.confidence == "exact"
        assert result.matched.last_name == "Smith"

    def test_case_insensitive(self):
        candidates = [_prof("John", "Smith")]
        result = match_professor("JOHN SMITH", candidates)
        assert result.is_matched
        assert result.confidence == "exact"

    def test_no_match(self):
        candidates = [_prof("Jane", "Doe")]
        result = match_professor("John Smith", candidates)
        assert not result.is_matched
        assert result.confidence == "none"

    def test_empty_candidates(self):
        result = match_professor("John Smith", [])
        assert not result.is_matched

    def test_fuzzy_first_name(self):
        candidates = [_prof("Jon", "Smith")]
        result = match_professor("John Smith", candidates)
        assert result.is_matched
        assert result.confidence == "fuzzy"

    def test_multiple_candidates_picks_best(self):
        candidates = [
            _prof("John", "Smith", num_ratings=5),
            _prof("John", "Smith", num_ratings=50),
        ]
        result = match_professor("John Smith", candidates)
        assert result.is_matched
        # Should pick the one with more ratings
        assert result.matched.num_ratings == 50

    def test_with_title_in_canvas_name(self):
        candidates = [_prof("John", "Smith")]
        result = match_professor("Dr. John Smith", candidates)
        assert result.is_matched
        assert result.confidence == "exact"
