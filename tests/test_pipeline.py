#!/usr/bin/env python3
"""
pytest suite for Canvas Reranker training pipeline.
Run with: pytest tests/ -v
"""
import json, os, sys, tempfile
from pathlib import Path

import pytest

# Add scripts dir to path
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from collect_rerank_dataset import (
    W_TIME, W_TYPE, W_POINTS, W_STATUS,
    _urgency, serialize_item, format_for_sft, format_for_dpo,
    anonymize_pairs, _anon_course, _anon_title
)
from run_pipeline import PipelineState

# Data lives in Gemma2B-Reranker
DATA_DIR = Path("/home/broklein/codeWS/Gemma2B-Reranker/data")


# ── Heuristic Weight Tests ──────────────────────────────────────────────────
class TestHeuristicWeights:
    def test_weights_match_benchmark(self):
        """Weights in collect_rerank_dataset.py must match benchmark.py."""
        bm_path = SCRIPT_DIR / "benchmark.py"
        bm_src = bm_path.read_text()
        weights = {"W_TIME": 3.0, "W_TYPE": 2.5, "W_POINTS": 1.5, "W_STATUS": 2.0}
        for var, val in weights.items():
            # Match both "W_TIME = 3.0" and "W_TIME   = 3.0" (flexible whitespace)
            import re
            pattern = rf"^{var}\s+=\s+{re.escape(str(val))}"
            found = bool(re.search(pattern, bm_src, re.MULTILINE))
            assert found, f"{var}={val} not found in benchmark.py (checked pattern: {pattern})"

    def test_weights_have_expected_values(self):
        assert W_TIME == 3.0
        assert W_TYPE == 2.5
        assert W_POINTS == 1.5
        assert W_STATUS == 2.0


# ── Heuristic / Urgency Tests ──────────────────────────────────────────────
class TestUrgency:
    def test_urgency_positive_for_future_item(self):
        item = {"due_at": "2026-04-20T23:00:00Z", "type": "assignment",
                "points_possible": 10, "has_submitted_submissions": False}
        u = _urgency(item)
        assert u > 0, f"Expected positive urgency, got {u}"

    def test_urgency_higher_when_closer(self):
        soon = {"hours_until_due": 24, "type": "assignment",
                "points_possible": 10, "has_submitted_submissions": False}
        far = {"hours_until_due": 240, "type": "assignment",
               "points_possible": 10, "has_submitted_submissions": False}
        assert _urgency(soon) > _urgency(far),             f"Closer ({_urgency(soon)}) should score higher than far ({_urgency(far)})"

    def test_urgency_exam_higher_than_homework(self):
        hw = {"due_at": "2026-04-16T23:00:00Z", "type": "assignment",
              "points_possible": 10, "has_submitted_submissions": False}
        exam = {"hours_until_due": 24, "type": "exam",
                "points_possible": 10, "has_submitted_submissions": False}
        assert _urgency(exam) > _urgency(hw),             f"Exam ({_urgency(exam)}) should beat HW ({_urgency(hw)})"

    def test_urgency_submitted_lower_than_open(self):
        open_item = {"due_at": "2026-04-16T23:00:00Z", "type": "assignment",
                     "points_possible": 10, "has_submitted_submissions": False}
        sub = {"hours_until_due": 24, "type": "assignment",
               "points_possible": 10, "has_submitted_submissions": True}
        assert _urgency(open_item) > _urgency(sub),             f"Open ({_urgency(open_item)}) should beat submitted ({_urgency(sub)})"

    def test_urgency_none_due_date(self):
        item = {"hours_until_due": 999, "type": "quiz",
                "points_possible": 5, "has_submitted_submissions": False}
        u = _urgency(item)
        assert u >= 0, f"Urgency should be non-negative, got {u}"


# ── Anonymization Tests ────────────────────────────────────────────────────
class TestAnonymization:
    def test_anon_course_idempotent(self):
        cid = 224083
        assert _anon_course(cid) == _anon_course(cid)

    def test_anon_course_deterministic(self):
        cid = 224083
        import hashlib
        h = int(hashlib.md5(str(cid).encode()).hexdigest()[:6], 16)
        expected = f"COURSE{str((h % 999) + 1).zfill(3)}"
        assert _anon_course(cid) == expected

    def test_anon_title_homogenizes_types(self):
        cases = [
            ("homework", "Homework"), ("Assignment 3", "Homework"),
            ("quiz", "Quiz"), ("Quiz 2", "Quiz"),
            ("exam", "Exam"), ("midterm", "Exam"),
            ("project", "Project"),
            (None, "Assignment"), ("", "Assignment"),
            ("Lab Report", "Assignment"),
        ]
        for inp, expected in cases:
            assert _anon_title(inp) == expected, f"_anon_title({inp!r})={_anon_title(inp)!r} != {expected!r}"

    def test_anon_pairs_no_reals(self):
        pair = {
            "item_a": {"course_id": 224083, "name": "Secret Course", "type": "homework",
                       "points_possible": 10, "due_at": "2026-04-16T23:00:00Z",
                       "has_submitted_submissions": False, "serialized": "Secret Course"},
            "item_b": {"course_id": 99999, "name": "Hidden Name", "type": "quiz",
                       "points_possible": 5, "due_at": "2026-04-15T23:00:00Z",
                       "has_submitted_submissions": False, "serialized": "Hidden Name"},
            "query": "What's due?", "preference": 1, "pair_type": "standard",
            "id": "anon_test_1", "reason": "test",
            "urgency_a": 4.5, "urgency_b": 3.2,
            "source_user": "test_user"
        }
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            json.dump(pair, f); f.write("\n")
            inp = f.name
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as out:
            o = out.name
        try:
            anonymize_pairs([pair], o)
            with open(o) as f:
                lines = [l for l in f if l.strip()]
            assert len(lines) == 1
            dump = json.dumps(json.loads(lines[0]))
            assert "Secret Course" not in dump
            assert "Hidden Name" not in dump
            assert "224083" not in dump
            assert "99999" not in dump
        finally:
            os.unlink(inp)
            if os.path.exists(o): os.unlink(o)


# ── DPO Export Tests ────────────────────────────────────────────────────────
class TestDpoExport:
    def test_dpo_fields(self):
        pair = {
            "item_a": {"name": "HW 1", "type": "assignment", "points_possible": 10,
                       "due_at": "2026-04-16T23:00:00Z", "course_id": 1,
                       "has_submitted_submissions": False, "serialized": "HW 1"},
            "item_b": {"name": "Quiz 1", "type": "quiz", "points_possible": 5,
                       "due_at": "2026-04-15T23:00:00Z", "course_id": 1,
                       "has_submitted_submissions": False, "serialized": "Quiz 1"},
            "query": "What's most urgent?", "preference": 1,
            "pair_type": "standard", "id": "test123",
            "reason": "HW 1 is more urgent because test reasoning"
        }
        out = format_for_dpo([pair])[0]
        assert isinstance(out, dict), f"Expected dict, got {type(out)}"
        d = out
        assert all(k in d for k in ["prompt", "chosen", "rejected", "id", "pair_type"])

    def test_dpo_preference_a_wins(self):
        pair = {
            "item_a": {"name": "A", "type": "exam", "points_possible": 100,
                       "due_at": "2026-04-15T23:00:00Z", "course_id": 1,
                       "has_submitted_submissions": False, "serialized": "A"},
            "item_b": {"name": "B", "type": "homework", "points_possible": 10,
                       "due_at": "2026-04-20T23:00:00Z", "course_id": 1,
                       "has_submitted_submissions": False, "serialized": "B"},
            "query": "What's most urgent?",
            "preference": 1, "pair_type": "standard", "id": "test456",
            "reason": "A is more urgent"
        }
        out = format_for_dpo([pair])[0]
        assert isinstance(out, dict), f"Expected dict, got {type(out)}"
        d = out
        assert "Item A" in d["chosen"] or "ITEM A" in d["chosen"].upper()

    def test_dpo_balanced(self):
        pairs = [
            {**p, "preference": i % 2, "reason": "test"}
            for i, p in enumerate([
                {"item_a": {"name": f"A{i}", "type": "hw", "points_possible": 10,
                            "due_at": "2026-04-16T23:00:00Z", "course_id": 1,
                            "has_submitted_submissions": False, "serialized": f"A{i}"},
                 "item_b": {"name": f"B{i}", "type": "quiz", "points_possible": 5,
                            "due_at": "2026-04-15T23:00:00Z", "course_id": 1,
                            "has_submitted_submissions": False, "serialized": f"B{i}"},
                 "query": "?", "pair_type": "standard", "id": f"t{i}"}
                for i in range(100)
            ])
        ]
        formatted = format_for_dpo(pairs)
        a_wins = sum(1 for f in formatted if isinstance(f, dict) and "Item A" in f.get("chosen",""))
        assert 40 <= a_wins <= 60, f"Imbalanced: {a_wins}/100 preferred A"


# ── SFT Export Tests ───────────────────────────────────────────────────────
class TestSftExport:
    def test_sft_has_eos_token(self):
        pair = {
            "item_a": {"name": "A", "type": "hw", "points_possible": 10,
                       "due_at": "2026-04-16T23:00:00Z", "course_id": 1,
                       "has_submitted_submissions": False, "serialized": "A"},
            "item_b": {"name": "B", "type": "quiz", "points_possible": 5,
                       "due_at": "2026-04-15T23:00:00Z", "course_id": 1,
                       "has_submitted_submissions": False, "serialized": "B"},
            "query": "What's most urgent?",
            "preference": 1, "pair_type": "standard", "id": "t1",
            "reason": "A is more urgent"
        }
        out = format_for_sft([pair], anonymize=False)[0]
        assert isinstance(out, dict), f"Expected dict, got {type(out)}"
        text = out.get("text", "")
        assert "<eos>" in text or "<|endoftext|>" in text, f"Missing EOS in: {text[:200]}"


# ── Pipeline State Tests ────────────────────────────────────────────────────
class TestPipelineState:
    def test_save_load_roundtrip(self):
        s = PipelineState(phase="path_a_1", path_a1_done=True,
                          best_score=0.82, started_at="2026-04-15T07:00:00Z")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            s.save(tmp)
            loaded = PipelineState.load(tmp)
            assert loaded.phase == "path_a_1"
            assert loaded.path_a1_done == True
            assert loaded.best_score == 0.82
        finally:
            os.unlink(tmp)

    def test_state_fields_complete(self):
        s = PipelineState()
        for field in ["phase", "path_a1_done", "path_a2_done", "path_b_done",
                      "benchmark_done", "best_adapter", "best_score",
                      "started_at", "completed_at"]:
            assert hasattr(s, field), f"Missing field: {field}"


# ── Data File Tests ────────────────────────────────────────────────────────
@pytest.mark.skipif(not DATA_DIR.exists(), reason="Local data only — requires Gemma2B-Reranker data at DATA_DIR")
class TestDataFiles:
    def test_rerank_train_exists_and_not_empty(self):
        p = DATA_DIR / "rerank_train.jsonl"
        assert p.exists(), f"Missing: {p}"
        pairs = [l for l in open(p) if l.strip()]
        assert len(pairs) >= 100, f"Too few train pairs: {len(pairs)}"

    def test_rerank_test_exists_and_not_empty(self):
        p = DATA_DIR / "rerank_test.jsonl"
        assert p.exists(), f"Missing: {p}"
        pairs = [l for l in open(p) if l.strip()]
        assert len(pairs) >= 50, f"Too few test pairs: {len(pairs)}"

    def test_train_pairs_have_required_fields(self):
        p = DATA_DIR / "rerank_train.jsonl"
        for line in open(p):
            if not line.strip(): continue
            d = json.loads(line)
            for k in ["query", "item_a", "item_b", "preference", "pair_type"]:
                assert k in d, f"Missing {k} in {d.get('id', 'unknown')}"

    def test_item_a_has_required_fields(self):
        p = DATA_DIR / "rerank_train.jsonl"
        for line in open(p):
            if not line.strip(): continue
            d = json.loads(line)
            ia = d["item_a"]
            for k in ["name", "type", "due_at", "points_possible",
                      "has_submitted_submissions", "serialized"]:
                assert k in ia, f"item_a missing {k} in pair {d.get('id')}"

    def test_hard_negative_pairs_exist(self):
        p = DATA_DIR / "rerank_train.jsonl"
        hard = [json.loads(l) for l in open(p) if l.strip()
                and json.loads(l).get("pair_type") == "hard_negative"]
        assert len(hard) >= 5, f"Too few hard negatives: {len(hard)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
