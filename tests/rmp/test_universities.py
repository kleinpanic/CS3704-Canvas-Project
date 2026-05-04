"""Tests for the university registry."""

import json
import tempfile
from pathlib import Path

import pytest

from canvas_tui.rmp.universities import UniversityRegistry, SEED_UNIVERSITIES


class TestUniversityRegistry:
    def test_find_by_canvas_url(self):
        reg = UniversityRegistry()
        vt = reg.find_by_canvas_url("https://canvas.vt.edu")
        assert vt is not None
        assert vt["name"] == "Virginia Tech"
        assert vt["rmp_school_id"] == 1346

    def test_find_by_canvas_url_trailing_slash(self):
        reg = UniversityRegistry()
        vt = reg.find_by_canvas_url("https://canvas.vt.edu/")
        assert vt is not None

    def test_find_by_name(self):
        reg = UniversityRegistry()
        vt = reg.find_by_name("Virginia Tech")
        assert vt is not None

    def test_find_by_alias(self):
        reg = UniversityRegistry()
        vt = reg.find_by_name("VT")
        assert vt is not None

    def test_find_by_name_case_insensitive(self):
        reg = UniversityRegistry()
        vt = reg.find_by_name("virginia tech")
        assert vt is not None

    def test_find_by_name_not_found(self):
        reg = UniversityRegistry()
        result = reg.find_by_name("Nonexistent University")
        assert result is None

    def test_find_by_rmp_id(self):
        reg = UniversityRegistry()
        vt = reg.find_by_rmp_id(1346)
        assert vt is not None
        assert vt["name"] == "Virginia Tech"

    def test_all_universities(self):
        reg = UniversityRegistry()
        all_unis = reg.all_universities()
        assert len(all_unis) == len(SEED_UNIVERSITIES)

    def test_user_overrides(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{
                "name": "Virginia Tech",
                "rmp_school_id": 9999,
            }], f)
            f.flush()
            path = Path(f.name)

        reg = UniversityRegistry(user_path=path)
        vt = reg.find_by_name("Virginia Tech")
        assert vt is not None
        assert vt["rmp_school_id"] == 9999

        path.unlink()

    def test_user_new_entry(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{
                "name": "Test University",
                "canvas_url": "https://canvas.test.edu",
                "rmp_school_id": 1234,
            }], f)
            f.flush()
            path = Path(f.name)

        reg = UniversityRegistry(user_path=path)
        tu = reg.find_by_name("Test University")
        assert tu is not None
        assert tu["rmp_school_id"] == 1234

        path.unlink()

    def test_add_university(self):
        reg = UniversityRegistry()
        reg.add_university({
            "name": "New University",
            "canvas_url": "https://canvas.new.edu",
            "rmp_school_id": 5555,
        })
        nu = reg.find_by_name("New University")
        assert nu is not None
        assert nu["rmp_school_id"] == 5555

    def test_add_university_missing_name_raises(self):
        reg = UniversityRegistry()
        with pytest.raises(ValueError):
            reg.add_university({"canvas_url": "https://canvas.test.edu"})
