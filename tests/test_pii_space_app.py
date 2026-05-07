# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for huggingface/pii-scrub/app.py — FastAPI PII scrub Space."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Skip these tests when the Space's runtime deps aren't installed in the env
# (CI runners outside the deploy-pii-space workflow won't have fastapi/uvicorn).
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("slowapi")

# ---------------------------------------------------------------------------
# Path setup: huggingface/pii-scrub/ is not a package; add it to sys.path so we can
# import app.py. We also need to mock transformers.pipeline before import.
# ---------------------------------------------------------------------------

_HF_SPACE_DIR = str(Path(__file__).resolve().parent.parent / "huggingface" / "pii-scrub")
if _HF_SPACE_DIR not in sys.path:
    sys.path.insert(0, _HF_SPACE_DIR)


def _make_mock_ner(entities=None):
    """Return a callable that mimics transformers.pipeline NER output."""
    if entities is None:
        entities = []
    return lambda text, **kw: entities


@pytest.fixture(autouse=True)
def _patch_ner():
    """Patch _ner in the app module with a controllable mock before each test."""
    import importlib

    mock_ner = _make_mock_ner()

    # Ensure app is freshly importable (may already be cached)
    if "app" in sys.modules:
        app_mod = sys.modules["app"]
        original_ner = app_mod._ner
        app_mod._ner = mock_ner
        yield app_mod
        app_mod._ner = original_ner
    else:
        # First import: mock pipeline before import
        fake_pipeline = lambda *a, **kw: mock_ner
        with patch.dict("sys.modules", {"transformers": types.SimpleNamespace(pipeline=fake_pipeline)}):
            import app as app_mod
        app_mod._ner = mock_ner
        yield app_mod
        # Remove from sys.modules so next test gets a fresh import if needed
        # (not strictly necessary since we restore _ner)


@pytest.fixture
def client(_patch_ner):
    from fastapi.testclient import TestClient
    return TestClient(_patch_ner.app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /scrub
# ---------------------------------------------------------------------------

class TestScrub:
    def test_scrub_benign_document(self, client, _patch_ner):
        _patch_ner._ner = _make_mock_ner([])
        resp = client.post("/scrub", json={"document": {"type": "todo_snapshot", "text": "Hello world"}})
        assert resp.status_code == 200
        data = resp.json()
        assert "document" in data
        assert "redactions" in data
        assert "registry" in data

    def test_scrub_course_snapshot_passes_through(self, client, _patch_ner):
        """course_snapshot type must pass through unmodified (no NER run)."""
        doc = {
            "type": "course_snapshot",
            "course_code": "@COURSE1",
            "text": "Alice Smith works here",
        }
        _patch_ner._ner = _make_mock_ner([])
        resp = client.post("/scrub", json={"document": doc})
        assert resp.status_code == 200
        result_doc = resp.json()["document"]
        assert result_doc["text"] == "Alice Smith works here"

    def test_scrub_person_entity_replaced(self, client, _patch_ner):
        """NER entity for a name produces @PERSON_1 token."""
        entities = [{"entity_group": "I-GIVENNAME", "score": 0.99, "word": "Alice", "start": 0, "end": 5}]
        _patch_ner._ner = _make_mock_ner(entities)
        resp = client.post("/scrub", json={"document": {"text": "Alice lives here"}})
        assert resp.status_code == 200
        data = resp.json()
        assert "@PERSON_1" in data["document"]["text"]
        assert "@PERSON_1" in data["registry"].values()

    def test_same_name_twice_same_token(self, client, _patch_ner):
        """Same name appearing twice in one document yields same @PERSON_N token."""
        entities = [
            {"entity_group": "I-GIVENNAME", "score": 0.99, "word": "Alice", "start": 0, "end": 5},
            {"entity_group": "I-GIVENNAME", "score": 0.99, "word": "Alice", "start": 12, "end": 17},
        ]
        _patch_ner._ner = _make_mock_ner(entities)
        resp = client.post("/scrub", json={"document": {"text": "Alice and Alice"}})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["registry"]) == 1
        assert list(data["registry"].keys()) == ["Alice"]

    def test_scrub_already_tokenized_course_not_double_replaced(self, client, _patch_ner):
        """Text already containing @COURSE_N spans must not be replaced."""
        # NER should not return @COURSE_N because of the check inside _anon_text
        entities = [{"entity_group": "I-CITY", "score": 0.9, "word": "@COURSE1", "start": 0, "end": 8}]
        _patch_ner._ner = _make_mock_ner(entities)
        resp = client.post("/scrub", json={"document": {"text": "@COURSE1 session"}})
        assert resp.status_code == 200
        # The @COURSE1 span should not be turned into @LOC_1 (the guard in _anon_text skips it)
        data = resp.json()
        assert "@COURSE1" in data["document"]["text"] or "@LOC_1" not in data["document"]["text"]

    def test_scrub_503_when_ner_none(self, client, _patch_ner):
        """If model failed to load, /scrub returns 503."""
        _patch_ner._ner = None
        resp = client.post("/scrub", json={"document": {"text": "test"}})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# /entities
# ---------------------------------------------------------------------------

class TestEntities:
    def test_entities_returns_list(self, client, _patch_ner):
        entities = [{"entity_group": "I-EMAIL", "score": 0.99, "word": "alice@x.com", "start": 0, "end": 11}]
        _patch_ner._ner = _make_mock_ner(entities)
        resp = client.post("/entities", json={"inputs": "alice@x.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["entity_group"] == "I-EMAIL"
        assert "score" in data[0]
        assert "word" in data[0]
        assert "start" in data[0]
        assert "end" in data[0]

    def test_entities_benign_returns_empty_list(self, client, _patch_ner):
        _patch_ner._ner = _make_mock_ner([])
        resp = client.post("/entities", json={"inputs": "Hello world"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_entities_503_when_ner_none(self, client, _patch_ner):
        _patch_ner._ner = None
        resp = client.post("/entities", json={"inputs": "test"})
        assert resp.status_code == 503
