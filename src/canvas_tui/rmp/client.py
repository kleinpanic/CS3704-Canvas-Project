"""Rate My Professors API client.

Fetches professor data from RateMyProfessors.com for a given school.
Configurable school ID via the university registry.

Uses the same scraping approach as tisuela/ratemyprof-api but with:
- configurable base URL (for future API changes)
- proper session management and rate limiting
- structured output using our models
- caching support
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional, Sequence

import requests

from .models import ProfessorRating
from .universities import UniversityRegistry

logger = logging.getLogger(__name__)

# Default RMP base URL — configurable for testing or if the site structure changes
DEFAULT_RMP_BASE_URL = "https://www.ratemyprofessors.com"

# Rate limiting: minimum seconds between requests to RMP
MIN_REQUEST_INTERVAL = 1.0

# Cache TTL in seconds (24 hours)
CACHE_TTL = 86400


class RMPClientError(Exception):
    """Base exception for RMP client errors."""

    pass


class RMPClient:
    """Client for fetching professor data from RateMyProfessors.com.

    Args:
        rmp_school_id: The RMP school ID to query.
        rmp_base_url: Base URL for RateMyProfessors (configurable).
        cache_dir: Optional directory for caching professor data.
        rate_limit: Minimum seconds between requests.
    """

    def __init__(
        self,
        rmp_school_id: int,
        rmp_base_url: str = DEFAULT_RMP_BASE_URL,
        cache_dir: Optional[Path] = None,
        rate_limit: float = MIN_REQUEST_INTERVAL,
    ):
        self.rmp_school_id = rmp_school_id
        self.rmp_base_url = rmp_base_url.rstrip("/")
        self.cache_dir = cache_dir
        self.rate_limit = rate_limit
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "CS3704-Canvas-Project/1.0 (Educational)",
            "Accept": "application/json, text/html, */*",
        })
        self._last_request_time: float = 0.0
        self._professors_cache: Optional[list[ProfessorRating]] = None

    @classmethod
    def from_canvas_url(
        cls,
        canvas_url: str,
        registry: Optional[UniversityRegistry] = None,
        cache_dir: Optional[Path] = None,
    ) -> Optional["RMPClient"]:
        """Create an RMPClient by looking up the school from a Canvas URL.

        Returns None if the Canvas URL is not in the registry.
        """
        reg = registry or UniversityRegistry()
        uni = reg.find_by_canvas_url(canvas_url)
        if uni is None:
            return None
        return cls(
            rmp_school_id=uni["rmp_school_id"],
            cache_dir=cache_dir,
        )

    def _rate_limit_wait(self) -> None:
        """Ensure we don't exceed the rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

    def _cache_path(self) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"rmp_{self.rmp_school_id}.json"

    def _load_cache(self) -> Optional[list[ProfessorRating]]:
        """Load professors from cache if available and not expired."""
        cache_file = self._cache_path()
        if cache_file is None or not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text())
            age = time.time() - data.get("timestamp", 0)
            if age > CACHE_TTL:
                logger.info("RMP cache expired for school %d", self.rmp_school_id)
                return None

            professors = []
            for entry in data.get("professors", []):
                professors.append(ProfessorRating(
                    rmp_id=entry["rmp_id"],
                    first_name=entry["first_name"],
                    last_name=entry["last_name"],
                    department=entry.get("department", ""),
                    rating=entry.get("rating", 0.0),
                    difficulty=entry.get("difficulty", 0.0),
                    num_ratings=entry.get("num_ratings", 0),
                    would_take_again_percent=entry.get("would_take_again_percent"),
                    url=f"{self.rmp_base_url}/professor/{entry['rmp_id']}",
                ))
            logger.info("Loaded %d professors from cache for school %d", len(professors), self.rmp_school_id)
            return professors
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load RMP cache: %s", e)
            return None

    def _save_cache(self, professors: list[ProfessorRating]) -> None:
        """Save professors to cache."""
        cache_file = self._cache_path()
        if cache_file is None:
            return

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": time.time(),
            "school_id": self.rmp_school_id,
            "professors": [
                {
                    "rmp_id": p.rmp_id,
                    "first_name": p.first_name,
                    "last_name": p.last_name,
                    "department": p.department,
                    "rating": p.rating,
                    "difficulty": p.difficulty,
                    "num_ratings": p.num_ratings,
                    "would_take_again_percent": p.would_take_again_percent,
                }
                for p in professors
            ],
        }
        cache_file.write_text(json.dumps(data, indent=2))

    def fetch_professors(self, force_refresh: bool = False) -> list[ProfessorRating]:
        """Fetch all professors for the configured school.

        Uses cache if available and not expired, unless force_refresh is True.
        Returns a list of ProfessorRating objects.
        """
        if not force_refresh:
            if self._professors_cache is not None:
                return self._professors_cache

            cached = self._load_cache()
            if cached is not None:
                self._professors_cache = cached
                return cached

        professors = self._scrape_professors()
        self._professors_cache = professors
        self._save_cache(professors)
        return professors

    def _scrape_professors(self) -> list[ProfessorRating]:
        """Scrape all professors for the school from RateMyProfessors."""
        professors: list[ProfessorRating] = []
        page = 1
        total_pages = 1  # Will be updated after first request

        while page <= total_pages:
            self._rate_limit_wait()
            url = (
                f"{self.rmp_base_url}/filter/professor/"
                f"?page={page}"
                f"&filter=teacherlastname_sort_s+asc"
                f"&query=*%3A*"
                f"&queryoption=TEACHER"
                f"&queryBy=schoolId"
                f"&sid={self.rmp_school_id}"
            )

            try:
                resp = self._session.get(url, timeout=30)
                self._last_request_time = time.time()
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.error("RMP request failed (page %d): %s", page, e)
                raise RMPClientError(f"Failed to fetch RMP data: {e}") from e

            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.error("RMP response was not JSON (page %d): %s", page, e)
                raise RMPClientError(f"RMP returned non-JSON response") from e

            # Parse pagination
            remaining = data.get("remaining", 0)
            total_professors = data.get("searchResultsTotal", 0)
            professors_per_page = 20  # RMP default
            if page == 1 and total_professors > 0:
                total_pages = (total_professors + professors_per_page - 1) // professors_per_page

            # Parse professor entries
            for entry in data.get("professors", []):
                prof = self._parse_professor_entry(entry)
                if prof is not None:
                    professors.append(prof)

            page += 1
            logger.info(
                "RMP scrape: school %d, page %d/%d, %d professors so far",
                self.rmp_school_id, page - 1, total_pages, len(professors),
            )

        return professors

    def _parse_professor_entry(self, entry: dict) -> Optional[ProfessorRating]:
        """Parse a single professor entry from the RMP API response."""
        try:
            rmp_id = int(entry.get("tid", 0))
            if rmp_id == 0:
                return None

            first_name = entry.get("tFname", "").strip()
            last_name = entry.get("tLname", "").strip()
            department = entry.get("tDept", "").strip()

            # Rating fields
            rating_str = entry.get("overall_rating", "0")
            try:
                rating = float(rating_str)
            except (ValueError, TypeError):
                rating = 0.0

            # Difficulty is in the ratings data
            difficulty = 0.0
            num_ratings = 0
            would_take_again = None

            # These may be in nested structures or direct fields depending on API version
            if "tNumRatings" in entry:
                try:
                    num_ratings = int(entry["tNumRatings"])
                except (ValueError, TypeError):
                    pass

            if "rDifficulty" in entry:
                try:
                    difficulty = float(entry["rDifficulty"])
                except (ValueError, TypeError):
                    pass

            if "rWouldTakeAgain" in entry:
                try:
                    val = entry["rWouldTakeAgain"]
                    if isinstance(val, str) and val.endswith("%"):
                        val = val[:-1]
                    would_take_again = float(val)
                except (ValueError, TypeError):
                    pass

            return ProfessorRating(
                rmp_id=rmp_id,
                first_name=first_name,
                last_name=last_name,
                department=department,
                rating=rating,
                difficulty=difficulty,
                num_ratings=num_ratings,
                would_take_again_percent=would_take_again,
                url=f"{self.rmp_base_url}/professor/{rmp_id}",
            )
        except Exception as e:
            logger.warning("Failed to parse RMP professor entry: %s", e)
            return None

    def search_professor(
        self,
        first_name: str,
        last_name: str,
        force_refresh: bool = False,
    ) -> list[ProfessorRating]:
        """Search for professors matching the given name.

        Fetches all professors for the school and filters by name.
        """
        all_profs = self.fetch_professors(force_refresh=force_refresh)
        first_lower = first_name.lower()
        last_lower = last_name.lower()

        matches = []
        for prof in all_profs:
            if prof.last_name.lower() == last_lower:
                if not first_lower or prof.first_name.lower() == first_lower:
                    matches.append(prof)
                elif first_lower in prof.first_name.lower():
                    matches.append(prof)

        return matches

    def get_professor_by_name(
        self,
        full_name: str,
        force_refresh: bool = False,
    ) -> Optional[ProfessorRating]:
        """Look up a single professor by full name.

        Returns the first match or None.
        """
        from .matcher import parse_first_last

        first, last = parse_first_last(full_name)
        matches = self.search_professor(first, last, force_refresh=force_refresh)
        return matches[0] if matches else None
