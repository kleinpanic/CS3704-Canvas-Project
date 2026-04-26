#!/usr/bin/env python3
"""
Privacy scrubber for Canvas DPO datasets.

Two layers of anonymization:

Layer 1 — Names wordlist (optional):
  Uses SecLists names.txt to find/replace personal names in any text field.
  Matches first names, last names as whole words. Deterministic.

Layer 2 — Metadata sanitization (always-on):
  The metadata header is where the real leak lives:
  - Course names reveal real course codes ("Intro Computer Organization I" = CS2505)
  - Course codes in metadata reveal what courses this person took
  - Handle/username reveals identity
  - Term info reveals when they took courses
  - Grade weights, exam dates reveal academic patterns

  This layer removes ALL of that and replaces with synthetic course metadata.

Usage:
  python3 scrub.py --input data/collab/user.jsonl --output data/collab/user_clean.jsonl

  Dry run (show what would change):
  python3 scrub.py --input data/collab/user.jsonl --dry-run

  With names wordlist (catches names that appear in text):
  python3 scrub.py --input data/collab/user.jsonl --output data/collab/user_clean.jsonl \
    --names https://raw.githubusercontent.com/danielmiessler/SecLists/master/Usernames/Names/names.txt
"""

import argparse
import json
import os
import random
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


# ── Layer 1: Names wordlist scrubber ─────────────────────────────────────────

@dataclass
class NameScrubber:
    names_source: str
    replacement_map: dict = field(default_factory=dict)
    counter: int = 0
    names: set = field(default_factory=set)
    _regex: Optional[re.Pattern] = None

    def load(self) -> None:
        print(f"Loading names: {self.names_source[:80]}")
        if self.names_source.startswith("http"):
            try:
                with urllib.request.urlopen(self.names_source, timeout=15) as resp:
                    content = resp.read().decode("utf-8", errors="ignore")
            except Exception as e:
                print(f"  Fetch failed: {e} — skipping wordlist")
                content = ""
        else:
            content = open(self.names_source).read() if os.path.exists(self.names_source) else ""

        self.names = set()
        for line in content.splitlines():
            line = line.strip().lower()
            if line and len(line) >= 2:
                self.names.add(line)

        if not self.names:
            print("  No names loaded")
            return

        print(f"  Loaded {len(self.names):,} names")
        sorted_names = sorted(self.names, key=len, reverse=True)
        self._regex = re.compile(
            r'\b(' + '|'.join(re.escape(n) for n in sorted_names) + r')\b',
            flags=re.IGNORECASE
        )

    def get_placeholder(self, name_lower: str) -> str:
        if name_lower not in self.replacement_map:
            self.counter += 1
            self.replacement_map[name_lower] = f"PERSON{self.counter:03d}"
        return self.replacement_map[name_lower]

    def apply(self, text: str) -> tuple[str, int]:
        """Replace names in text. Returns (cleaned_text, replacement_count)."""
        if not self._regex or not text:
            return text, 0

        count = [0]  # nonlocal counter

        def replacer(m):
            placeholder = self.get_placeholder(m.group(0).lower())
            count[0] += 1
            return placeholder

        cleaned = self._regex.sub(replacer, text)
        return cleaned, count[0]


# ── Layer 2: Metadata sanitization ─────────────────────────────────────────────

# Synthetic course metadata — replaces real course names
COURSE_TYPES = ["cs_core", "science_lab", "humanities", "elective", "health_sci", "business", "arts"]
SYNTHETIC_COURSE_PREFIXES = ["DATA_STRUCTURE", "ALGORITHM", "PROGRAM", "LAB", "RESEARCH", "SEMINAR", "PRACTICUM"]

def _synthesize_course_meta(code: str) -> dict:
    """Replace real course metadata with synthetic values."""
    course_num = int(code.replace("COURSE", "").lstrip("0") or "0")
    rng = random.Random(code)  # deterministic per course code

    return {
        "code": code,
        "name": f"{rng.choice(SYNTHETIC_COURSE_PREFIXES)} {rng.randint(1000, 4999)}",
        "course_type": rng.choice(COURSE_TYPES),
        "grade_weights": {
            "exams": rng.randint(30, 50),
            "assignments": rng.randint(20, 40),
            "participation": rng.randint(5, 15),
        },
        "exam_dates": [f"2025-0{rng.randint(1,9)}-{rng.randint(10,28)}" for _ in range(rng.randint(1, 3))],
        "credits": rng.choice([3, 4]),
        "term": f"{rng.choice(['Fall', 'Spring', 'Summer'])} {rng.choice([2022, 2023, 2024, 2025])}",
    }


def sanitize_metadata(meta: dict) -> tuple[dict, list[str]]:
    """
    Remove all personally-reidentifiable information from metadata header.
    Returns (sanitized_metadata, list_of_changes_made).
    """
    changes = []

    # Build inverse course map
    course_map = meta.get("course_map", {})
    inv_map = {v: k for k, v in course_map.items()}  # code → cid

    # Replace handle with anonymous
    if meta.get("handle"):
        changes.append(f"handle: '{meta['handle']}' → anonymized")
        meta["handle"] = f"user_{meta['handle'][0]}xxx"

    # Replace generated_at — keep the date format but genericize time
    if meta.get("generated_at"):
        changes.append("generated_at: stripped (contains timestamp)")
        meta["generated_at"] = "REDACTED"

    # Replace all course metadata with synthetic values
    old_courses = meta.get("courses", [])
    new_courses = []
    for c in old_courses:
        old_name = c.get("name", "")
        code = c.get("code", "")
        new_c = _synthesize_course_meta(code)
        new_courses.append(new_c)
        if old_name:
            changes.append(f"course name '{old_name}' → '{new_c['name']}'")

    meta["courses"] = new_courses

    # Replace course_map: old course_id → COURSE001 becomes cid → COURSE001
    # (The old map already has this — just verify it doesn't have name leaks)
    # The map itself only has cid→code, no name — that's fine
    # But regenerate it to be sure
    new_course_map = {int(cid_str): code for code, cid_str
                     in zip([c["code"] for c in new_courses],
                            [str(i+1).zfill(3) for i in range(len(new_courses))])}
    meta["course_map"] = new_course_map

    # Strip n_items and n_pairs (too specific — could hint at data volume)
    meta.pop("n_items", None)
    meta.pop("n_pairs", None)

    # Strip seed (irrelevant for shared data)
    meta.pop("seed", None)
    meta.pop("min_diff", None)

    return meta, changes


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Privacy scrubber for Canvas DPO datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scrubs two layers:
  1. Metadata header — removes course names, handles, terms, timestamps
  2. Names wordlist — replaces personal names in any text field

Usage:
  python3 scrub.py --input data/collab/user.jsonl --output data/collab/user_clean.jsonl
  python3 scrub.py --input data/collab/user.jsonl --dry-run
  python3 scrub.py --input data/collab/user.jsonl --names /path/to/names.txt
        """,
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--names", default="", help="URL or path to names wordlist (optional)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show-changes", type=int, default=50, help="Show top N changes (default: 50)")
    args = parser.parse_args()

    print("=== Privacy Scrubber ===")
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print()

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    # ── Layer 2: Sanitize metadata (always runs first) ─────────────────────────
    with open(args.input) as f:
        raw_lines = [l for l in f if l.strip()]

    meta = json.loads(raw_lines[0])
    pairs = raw_lines[1:]

    print("Layer 2: Sanitizing metadata header...")
    sanitized_meta, meta_changes = sanitize_metadata(dict(meta))
    print(f"  {len(meta_changes)} metadata changes")

    # Show first N changes
    for change in meta_changes[:args.show_changes]:
        print(f"    {change}")
    if len(meta_changes) > args.show_changes:
        print(f"    ... and {len(meta_changes) - args.show_changes} more")

    # ── Layer 1: Names wordlist (optional) ───────────────────────────────────
    name_scrubber = NameScrubber(args.names) if args.names else None
    text_changes = 0

    if name_scrubber and args.names:
        print(f"\nLayer 1: Loading names wordlist...")
        name_scrubber.load()

        print("Scanning pairs for name occurrences...")
        for line in pairs:
            record = json.loads(line)
            for field_path in ["query", "item_a.anon_title", "item_b.anon_title"]:
                parts = field_path.split(".")
                val = record
                for p in parts:
                    val = val.get(p, "")
                if val:
                    _, n = name_scrubber.apply(str(val))
                    text_changes += n

        print(f"  Names wordlist: {text_changes} replacements in text fields")
        if name_scrubber.replacement_map:
            top = sorted(name_scrubber.replacement_map.items(), key=lambda x: -1)[:10]
            for orig, repl in top:
                print(f"    {orig} → {repl}")

    print(f"\nTotal changes: {len(meta_changes)} metadata + {text_changes} text")

    if args.dry_run:
        print("\n[dry-run — no file written]")
        return

    # Write output
    print(f"\nWriting: {args.output}")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        f.write(json.dumps(sanitized_meta, ensure_ascii=False) + "\n")
        for line in pairs:
            if not line.strip():
                f.write(line)
                continue
            record = json.loads(line)

            # Apply name scrubber if loaded
            if name_scrubber and name_scrubber._regex:
                record["query"] = name_scrubber.apply(str(record.get("query", "")))[0]
                for item_key in ["item_a", "item_b"]:
                    if item_key in record and "anon_title" in record[item_key]:
                        record[item_key]["anon_title"] = name_scrubber.apply(
                            str(record[item_key]["anon_title"])
                        )[0]

            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Save change map
    map_path = args.output + ".scrub-map.json"
    with open(map_path, "w") as f:
        json.dump({
            "metadata_changes": meta_changes,
            "name_replacements": name_scrubber.replacement_map if name_scrubber else {},
        }, f, indent=2)
    print(f"Scrub map saved: {map_path}")
    print(f"\nDone. Output: {args.output}")


if __name__ == "__main__":
    main()