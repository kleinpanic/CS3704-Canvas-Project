"""Seeded university database.

Each entry maps a human-readable school name to:
- canvas_url: the Canvas LMS base URL for that school
- rmp_school_id: the RateMyProfessors.com school ID used for lookups
- aliases: alternative names for fuzzy matching

Users can add their own entries via config or CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Default seed data — populated from public RMP school search results.
# To find a school ID: visit https://www.ratemyprofessors.com/search.jsp?query=SchoolName
# and inspect the sid parameter or network requests.
SEED_UNIVERSITIES: list[dict] = [
    {
        "name": "Virginia Tech",
        "canvas_url": "https://canvas.vt.edu",
        "rmp_school_id": 1346,
        "aliases": ["Virginia Polytechnic Institute and State University", "VT", "VPI"],
    },
    {
        "name": "University of Virginia",
        "canvas_url": "https://canvas.virginia.edu",
        "rmp_school_id": 1413,
        "aliases": ["UVA", "University of Virginia"],
    },
    {
        "name": "University of Texas at Austin",
        "canvas_url": "https://canvas.utexas.edu",
        "rmp_school_id": 1055,
        "aliases": ["UT Austin", "UT"],
    },
    {
        "name": "University of Michigan",
        "canvas_url": "https://canvas.umich.edu",
        "rmp_school_id": 1223,
        "aliases": ["UMich", "Michigan"],
    },
    {
        "name": "Georgia Tech",
        "canvas_url": "https://canvas.gatech.edu",
        "rmp_school_id": 3688,
        "aliases": ["Georgia Institute of Technology", "GT"],
    },
    {
        "name": "UC Berkeley",
        "canvas_url": "https://canvas.berkeley.edu",
        "rmp_school_id": 1070,
        "aliases": ["University of California Berkeley", "Cal"],
    },
    {
        "name": "UCLA",
        "canvas_url": "https://canvas.ucla.edu",
        "rmp_school_id": 1072,
        "aliases": ["University of California Los Angeles"],
    },
    {
        "name": "MIT",
        "canvas_url": "https://canvas.mit.edu",
        "rmp_school_id": 1228,
        "aliases": ["Massachusetts Institute of Technology"],
    },
    {
        "name": "Stanford University",
        "canvas_url": "https://canvas.stanford.edu",
        "rmp_school_id": 1380,
        "aliases": ["Stanford"],
    },
    {
        "name": "Ohio State University",
        "canvas_url": "https://canvas.osu.edu",
        "rmp_school_id": 1313,
        "aliases": ["OSU", "Ohio State"],
    },
    {
        "name": "Penn State",
        "canvas_url": "https://canvas.psu.edu",
        "rmp_school_id": 1328,
        "aliases": ["Pennsylvania State University", "PSU"],
    },
    {
        "name": "Purdue University",
        "canvas_url": "https://canvas.purdue.edu",
        "rmp_school_id": 1342,
        "aliases": ["Purdue"],
    },
    {
        "name": "University of Florida",
        "canvas_url": "https://canvas.ufl.edu",
        "rmp_school_id": 1091,
        "aliases": ["UF", "Florida"],
    },
    {
        "name": "University of Illinois Urbana-Champaign",
        "canvas_url": "https://canvas.illinois.edu",
        "rmp_school_id": 1112,
        "aliases": ["UIUC", "Illinois"],
    },
    {
        "name": "Texas A&M University",
        "canvas_url": "https://canvas.tamu.edu",
        "rmp_school_id": 1047,
        "aliases": ["TAMU", "Texas A&M", "A&M"],
    },
]


class UniversityRegistry:
    """Manages the university database.

    Loads seed data and merges with any user-provided overrides from a JSON file.
    """

    def __init__(self, user_path: Optional[Path] = None):
        self._universities: list[dict] = list(SEED_UNIVERSITIES)
        self._user_path = user_path
        if user_path and user_path.exists():
            self._load_user_overrides(user_path)

    def _load_user_overrides(self, path: Path) -> None:
        with open(path) as f:
            user_data = json.load(f)
        if isinstance(user_data, list):
            for entry in user_data:
                if "name" in entry and ("canvas_url" in entry or "rmp_school_id" in entry):
                    # Replace if name matches, otherwise append
                    idx = next(
                        (i for i, u in enumerate(self._universities) if u["name"] == entry["name"]),
                        None,
                    )
                    if idx is not None:
                        self._universities[idx].update(entry)
                    else:
                        self._universities.append(entry)

    def find_by_canvas_url(self, canvas_url: str) -> Optional[dict]:
        """Look up a university by its Canvas LMS base URL."""
        normalized = canvas_url.rstrip("/").lower()
        for uni in self._universities:
            if uni.get("canvas_url", "").rstrip("/").lower() == normalized:
                return uni
        return None

    def find_by_name(self, name: str) -> Optional[dict]:
        """Look up a university by name or alias (case-insensitive substring match)."""
        name_lower = name.lower()
        for uni in self._universities:
            if name_lower in uni["name"].lower():
                return uni
            if "aliases" in uni:
                for alias in uni["aliases"]:
                    if name_lower in alias.lower():
                        return uni
        return None

    def find_by_rmp_id(self, rmp_school_id: int) -> Optional[dict]:
        """Look up a university by its RMP school ID."""
        for uni in self._universities:
            if uni.get("rmp_school_id") == rmp_school_id:
                return uni
        return None

    def all_universities(self) -> list[dict]:
        """Return all registered universities."""
        return list(self._universities)

    def add_university(self, entry: dict) -> None:
        """Add or update a university entry."""
        if "name" not in entry:
            raise ValueError("University entry must have a 'name' field")
        idx = next(
            (i for i, u in enumerate(self._universities) if u["name"] == entry["name"]),
            None,
        )
        if idx is not None:
            self._universities[idx].update(entry)
        else:
            self._universities.append(entry)
