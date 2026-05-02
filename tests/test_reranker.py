"""Tests for canvas_tui.reranker — Protocol compliance + serialize_item bridge.

The 18 tests here mirror the .planning/phases/01.1-01-SUMMARY.md
acceptance criteria from the upstream phase plan. They do NOT load any
GGUF model; LocalReranker is exercised at the constructor/SHA-check
level only.
"""
from __future__ import annotations

import pytest

from canvas_tui.models import CanvasItem, serialize_item
from canvas_tui.reranker import (
    AlwaysAReranker,
    LocalReranker,
    NullReranker,
    RANK_PROMPT_FORMAT_SHA,
    RANK_PROMPT_TEMPLATE,
    Reranker,
)


# ── Protocol compliance ──────────────────────────────────────────────


class TestProtocolCompliance:
    def test_null_reranker_is_reranker(self):
        assert isinstance(NullReranker(), Reranker)

    def test_always_a_reranker_is_reranker(self):
        assert isinstance(AlwaysAReranker(), Reranker)

    def test_local_reranker_is_reranker(self):
        assert isinstance(LocalReranker("/tmp/dummy.gguf"), Reranker)


# ── NullReranker ─────────────────────────────────────────────────────


class TestNullReranker:
    def test_returns_list(self):
        items = [CanvasItem(title="a"), CanvasItem(title="b")]
        result = NullReranker().rank("any", items)
        assert isinstance(result, list)
        assert result is not items  # new list, not same reference

    def test_preserves_all_items(self):
        items = [CanvasItem(title=t) for t in "xyz"]
        result = NullReranker().rank("any", items)
        assert len(result) == 3
        assert [i.title for i in result] == ["x", "y", "z"]

    def test_empty_input(self):
        assert NullReranker().rank("any", []) == []


# ── AlwaysAReranker ──────────────────────────────────────────────────


class TestAlwaysAReranker:
    def test_first_item_is_first(self):
        items = [CanvasItem(title="alpha"), CanvasItem(title="beta")]
        result = AlwaysAReranker().rank("any", items)
        assert result[0].title == "alpha"

    def test_returns_all_items(self):
        items = [CanvasItem(title=t) for t in "ABC"]
        result = AlwaysAReranker().rank("any", items)
        assert {i.title for i in result} == {"A", "B", "C"}


# ── LocalReranker skeleton ───────────────────────────────────────────


class TestLocalRerankerSkeleton:
    def test_call_model_raises_without_dep_or_model(self):
        # Empty model_path → NotImplementedError on first inference.
        r = LocalReranker("")
        with pytest.raises(NotImplementedError):
            r.rank("any", [CanvasItem(title="x")])

    def test_sha_mismatch_raises(self):
        with pytest.raises(ValueError, match="SHA"):
            LocalReranker("/tmp/x.gguf", expected_sha="0" * 64)

    def test_sha_match_no_raise(self):
        # Constructing with the correct SHA must not raise.
        LocalReranker("/tmp/x.gguf", expected_sha=RANK_PROMPT_FORMAT_SHA)


# ── SHA anti-drift ───────────────────────────────────────────────────


class TestSHAAntiDrift:
    def test_sha_is_64_chars(self):
        assert len(RANK_PROMPT_FORMAT_SHA) == 64

    def test_sha_is_hex(self):
        int(RANK_PROMPT_FORMAT_SHA, 16)  # raises if non-hex

    def test_sha_matches_expected(self):
        # If the trained template ever changes, this constant changes
        # and consumers asserting against the upstream training pipeline
        # SHA will fail loudly. Update this constant only when the
        # model is also retrained on the new template.
        import hashlib
        expected = hashlib.sha256(RANK_PROMPT_TEMPLATE.encode("utf-8")).hexdigest()
        assert RANK_PROMPT_FORMAT_SHA == expected

    def test_sha_changes_on_template_change(self):
        # Sanity: a single-character change must produce a different hash.
        import hashlib
        modified = RANK_PROMPT_TEMPLATE + "."
        sha2 = hashlib.sha256(modified.encode("utf-8")).hexdigest()
        assert sha2 != RANK_PROMPT_FORMAT_SHA


# ── serialize_item bridge ────────────────────────────────────────────


class TestSerializeItemBridge:
    def test_serialize_returns_string(self):
        item = CanvasItem(ptype="assignment", title="HW", course_code="CS 3704", points=100)
        result = serialize_item(item)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_serialize_contains_title(self):
        item = CanvasItem(ptype="assignment", title="UnitTestTitle", course_code="C", points=10)
        assert "UnitTestTitle" in serialize_item(item)

    def test_serialize_reachable_from_models(self):
        # The Phase 01.1-01 SUMMARY explicitly requires re-export
        # from canvas_tui.models — the same import path the training
        # pipeline uses.
        from canvas_tui.models import serialize_item as si
        assert si is serialize_item

    def test_serialize_anonymizes_course_code(self):
        # The trained model expects @COURSE#### not real codes; the
        # anonymizer is deterministic so the same course always maps
        # to the same opaque ID.
        item = CanvasItem(ptype="assignment", title="x", course_code="CS 3704", points=1)
        out = serialize_item(item)
        assert "@COURSE" in out
        assert "CS 3704" not in out and "@CS" not in out

    def test_serialize_uses_done_for_submitted(self):
        item = CanvasItem(
            ptype="quiz", title="q", course_code="CS 1", points=10,
            status_flags=["submitted"],
        )
        assert "DONE" in serialize_item(item)

    def test_serialize_omits_points_when_zero(self):
        item = CanvasItem(ptype="event", title="meeting", course_code="X", points=0)
        out = serialize_item(item)
        assert "0pts" not in out
