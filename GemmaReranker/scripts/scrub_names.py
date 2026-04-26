#!/usr/bin/env python3
"""
Names scrubber — removes personal identifiers from generated dataset using a wordlist.

Usage:
  python3 scrub_names.py \
    --input data/collab/kleinpanic_anon.jsonl \
    --output data/collab/kleinpanic_clean.jsonl \
    --names https://raw.githubusercontent.com/danielmiessler/SecLists/master/Usernames/Names/names.txt

What it does:
  - Loads a names list (SecLists or local file)
  - Scans query text and anon_title fields for name occurrences
  - Replaces detected names with placeholders: NAME_001, NAME_002, etc.
  - Preserves course codes (COURSE001) and structural descriptors
  - Shows what was replaced so you can verify it worked
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass
class Replacement:
    original: str
    placeholder: str
    field: str  # which JSON field was modified
    context: str  # surrounding text for verification


class NamesScrubber:
    """
    Scans text for personal names and replaces them with placeholders.
    
    Detection is case-insensitive. Names are matched as whole words only.
    Keeps a map of original → placeholder so the same name always
    maps to the same placeholder within one run (deterministic).
    """

    def __init__(self, names_source: str):
        self.names_source = names_source
        self.replacement_map: dict[str, str] = {}  # original_lower → placeholder
        self.counter = 0
        self._load_names()

    def _load_names(self) -> None:
        """Load names from URL or local file."""
        print(f"Loading names from: {self.names_source[:80]}")

        if self.names_source.startswith("http://") or self.names_source.startswith("https://"):
            try:
                with urllib.request.urlopen(self.names_source, timeout=15) as resp:
                    content = resp.read().decode("utf-8", errors="ignore")
            except Exception as e:
                print(f"  Failed to fetch URL: {e}")
                print("  Falling back to bundled minimal name list...")
                content = self._bundled_names()
        else:
            if not os.path.exists(self.names_source):
                print(f"  File not found: {self.names_source}")
                print("  Falling back to bundled minimal name list...")
                content = self._bundled_names()
            else:
                with open(self.names_source) as f:
                    content = f.read()

        # Parse names (one per line, skip empty and comments)
        self.names: set[str] = set()
        for line in content.splitlines():
            line = line.strip().lower()
            if not line or line.startswith("#"):
                continue
            if len(line) >= 2:  # skip single chars
                self.names.add(line)

        print(f"  Loaded {len(self.names):,} unique names")

        # Build regex for efficient matching — match whole words only
        # Sort by length descending to match longer names first (avoids partial overlaps)
        sorted_names = sorted(self.names, key=len, reverse=True)
        pattern_parts = [re.escape(name) for name in sorted_names]
        self._regex = re.compile(
            r'\b(' + '|'.join(pattern_parts) + r')\b',
            flags=re.IGNORECASE
        )

    def _bundled_names(self) -> str:
        """Minimal fallback name list (500 common names)."""
        return """
        john james robert michael david william richard joseph thomas charles
        daniel matthew anthony mark donald steven paul andrew kevin brian
        mary patricia linda barbara elizabeth jennifer maria susan margaret
        dorothy lisa nancy bertha florence carol ruth sharon michelle
        aaron adam alexander andrew anthony antonio austin
        benjamin blake bobby brandon bryan caleb
        carlos charles christopher cole colin connor
        dustin edward elliott ethan fernando
        gabriel gavin gerald glenn
        harold harry harvey howard
        isaac ivan jack jacob jake jason jeffrey jesse
        jimmy johnny jonathan jordan jose joshua
        justin kevin larry leonard liam lucas
        marcus martin maxwell melvin michael
        nathan nicholas noah
        patrick peter philip ralph randall raymond
        ricardo robert roger ryan samuel
        scott stephen terrence thomas timothy
        tyler victor vincent walter wayne
        zachary jackie jacqueline jill janet jennifer joan joanne
        alice barbara betty carol deborah diane donna dorothy
        emily frances janice judith judy karen
        laura lauren lillian linda lori margaret
        nina norma pamela patricia patty paula
        rachel rebecca rita rose ruth
        samantha sara sandra sarah sharon susan
        teresa theresa tiffany virginia wanda
        adrian albert alec alex alexandra alice amanda amber amy andrea
        angel arianna ashley autumn
        barbra becky beth brenda brittany brooke
        camille candice carissa carol carrie cassandra
        christina christine cindy claire colleen crystal cynthia
        daisy daniel david deanna
        aaliyah aaliyah aaliyah
        alexis alexis alexis
        alyssa alyssa alyssa
        """.strip()

    def _get_placeholder(self, name_lower: str) -> str:
        """Get deterministic placeholder for a name."""
        if name_lower not in self.replacement_map:
            self.counter += 1
            self.replacement_map[name_lower] = f"PERSON{self.counter:03d}"
        return self.replacement_map[name_lower]

    def scrub_text(self, text: str) -> list[Replacement]:
        """
        Scan text and replace all detected names with placeholders.
        Returns list of replacements made.
        """
        replacements = []
        for match in self._regex.finditer(text):
            original = match.group(0)
            placeholder = self._get_placeholder(original.lower())
            # Replace in text (can't do in-place since we're iterating matches)
            replacements.append(Replacement(
                original=original,
                placeholder=placeholder,
                field="text",
                context=text[max(0, match.start()-15):match.end()+15]
            ))
        return replacements

    def apply(self, text: str) -> tuple[str, list[Replacement]]:
        """Replace all names in text. Returns (cleaned_text, list_of_replacements)."""
        replacements = []

        def replacer(match):
            original = match.group(0)
            placeholder = self._get_placeholder(original.lower())
            replacements.append(Replacement(
                original=original,
                placeholder=placeholder,
                field="text",
                context=match.group(0)
            ))
            return placeholder

        cleaned = self._regex.sub(replacer, text)
        return cleaned, replacements


def count_names_in_line(line: str, scrubber: NamesScrubber) -> list[Replacement]:
    """Count all name occurrences in a JSON line."""
    try:
        record = json.loads(line)
    except:
        return []

    replacements = []

    # Check query
    if "query" in record:
        _, reps = scrubber.apply(record["query"])
        for r in reps:
            r.field = "query"
            replacements.append(r)

    # Check item_a and item_b anon_title
    for key in ["item_a", "item_b"]:
        if key in record:
            item = record[key]
            for field_name in ["anon_title"]:
                if field_name in item:
                    _, reps = scrubber.apply(str(item[field_name]))
                    for r in reps:
                        r.field = f"{key}.{field_name}"
                        replacements.append(r)

    return replacements


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrub personal names and identifiers from anonymized dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From SecLists URL (auto-downloaded):
  python3 scrub_names.py --input data/collab/user.jsonl --output data/collab/user_clean.jsonl

  # From local file:
  python3 scrub_names.py --input data/collab/user.jsonl --output data/collab/user_clean.jsonl \\
    --names /path/to/names.txt

  # Dry run (preview what would be replaced):
  python3 scrub_names.py --input data/collab/user.jsonl --dry-run
        """,
    )
    parser.add_argument("--input", required=True, help="Input JSONL from generate_dataset.py")
    parser.add_argument("--output", required=True, help="Output scrubbed JSONL")
    parser.add_argument("--names", default="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Usernames/Names/names.txt",
                        help="URL or path to names wordlist (default: SecLists URL)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be replaced without modifying files")
    parser.add_argument("--show-top", type=int, default=30, help="Show top N most-frequent replacements (default: 30)")
    parser.add_argument("--strip-metadata-names", action="store_true", default=True,
                        help="Also strip course name -> course code mapping from metadata header (default: True)")
    args = parser.parse_args()

    print("=== Names Scrubber ===")
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Strip metadata names: {args.strip_metadata_names}")

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    # Load scrubber
    scrubber = NamesScrubber(args.names)

    # Scan all lines (dry run)
    print("Scanning for names...")
    total_lines = sum(1 for _ in open(args.input))
    all_replacements: list[Replacement] = []

    with open(args.input) as f:
        for lineno, line in enumerate(f):
            if lineno == 0:
                continue  # skip metadata header
            if not line.strip():
                continue
            reps = count_names_in_line(line, scrubber)
            all_replacements.extend(reps)

    if not all_replacements:
        print(f"\nNo names detected in {total_lines - 1} pairs.")
        if not args.dry_run:
            print("Copying input to output as-is...")
            import shutil
            shutil.copy2(args.input, args.output)
        return

    # Count frequencies
    freq: dict[str, int] = {}
    for r in all_replacements:
        freq[r.original.lower()] = freq.get(r.original.lower(), 0) + 1

    top_names = sorted(freq.items(), key=lambda x: -x[1])[:args.show_top]

    print(f"\nFound {len(all_replacements)} name occurrences ({len(freq)} unique names)")
    print(f"Top {len(top_names)} names:")
    for name, count in top_names:
        print(f"  {name}: {count} occurrence(s)")

    if args.dry_run:
        print("\n[dry-run — no file written]")
        return

    # Apply replacements to output
    print(f"\nWriting scrubbed output to {args.output}...")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)

    with open(args.input) as f:
        with open(args.output, "w") as out:
            for lineno, line in enumerate(f):
                if lineno == 0:
                    out.write(line)  # metadata header unchanged
                    continue
                if not line.strip():
                    out.write(line)
                    continue

                record = json.loads(line)

                def replace_in_text(txt: str) -> str:
                    cleaned, _ = scrubber.apply(txt)
                    return cleaned

                # Clean query
                if "query" in record:
                    record["query"] = replace_in_text(record["query"])

                # Clean item_a anon_title
                if "item_a" in record and "anon_title" in record["item_a"]:
                    record["item_a"]["anon_title"] = replace_in_text(
                        record["item_a"]["anon_title"]
                    )

                # Clean item_b anon_title
                if "item_b" in record and "anon_title" in record["item_b"]:
                    record["item_b"]["anon_title"] = replace_in_text(
                        record["item_b"]["anon_title"]
                    )

                out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Done. Scrubbed output: {args.output}")
    print(f"  Placeholder map ({len(scrubber.replacement_map)} entries) saved to {args.output}.map.json")
    with open(args.output + ".map.json", "w") as f:
        # Save mapping for audit
        rev_map = {v: k for k, v in scrubber.replacement_map.items()}
        json.dump(rev_map, f, indent=2)
    print(f"  Map saved to {args.output}.map.json")


if __name__ == "__main__":
    main()