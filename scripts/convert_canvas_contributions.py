# SPDX-License-Identifier: GPL-3.0-or-later
"""
convert_canvas_contributions.py — convert share_my_canvas.py output to canvas_items format.

Reads JSONL files produced by classmates running share_my_canvas.py
(from data/collab/ or a path you specify) and converts
each assignment into the flat canvas_items schema used by the v4+
training pipeline.

Output schema (one line per assignment):
  {
    "item_id":        <sha256[:12] of type|title|course>,
    "contributor":    <contributor_id from source file>,
    "type":           "ASGN" | "QUIZ" | "DISC",
    "title":          <assignment name>,
    "course":         "@COURSE1",
    "due_offset_days":<int, days from collection time; negative = overdue>,
    "points":         <float>,
    "status":         "OVERDUE" | "Tomorrow" | "<N>d",
    "source":         "collab:<filename>"
  }

Usage:
    python3 scripts/convert_canvas_contributions.py \\
        --input  data/collab/ \\
        --output data/canvas_items_collab.jsonl

Then merge into the main items file:
    cat data/canvas_items_v4.jsonl data/canvas_items_collab.jsonl | \\
        sort -u > /tmp/merged.jsonl && mv /tmp/merged.jsonl data/canvas_items_v5.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


_SUBMISSION_TYPE_MAP = {
    "online_quiz":       "QUIZ",
    "online_upload":     "ASGN",
    "online_text_entry": "ASGN",
    "discussion_topic":  "DISC",
    "media_recording":   "ASGN",
    "none":              "ASGN",
}


def _item_type(submission_types: list[str]) -> str:
    for t in (submission_types or []):
        mapped = _SUBMISSION_TYPE_MAP.get(t)
        if mapped:
            return mapped
    return "ASGN"


def _item_key(itype: str, title: str, course: str) -> str:
    return hashlib.sha256(f"{itype}|{title.strip()}|{course}".encode()).hexdigest()[:12]


def _offset_to_status(offset: int) -> str:
    if offset < 0:
        return "OVERDUE"
    if offset == 1:
        return "Tomorrow"
    return f"{offset}d"


def convert_file(path: Path, seen: set[str]) -> list[dict]:
    items = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)

        if rec.get("type") != "course_snapshot":
            continue

        contributor = rec.get("contributor_id", "unknown")
        course = rec.get("course_code") or rec.get("course_name") or "COURSE?"
        if not course.startswith("@"):
            course = f"@{course}"

        collected_at_str = rec.get("collected_at", "")
        try:
            collected_at = datetime.fromisoformat(collected_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            collected_at = datetime.now(timezone.utc)

        for asgn in rec.get("assignments") or []:
            title = (asgn.get("name") or "").strip()
            points_raw = asgn.get("points_possible")
            due_str = asgn.get("due_at") or ""
            sub_types = asgn.get("submission_types") or []

            if not title or points_raw is None:
                continue
            pts = float(points_raw)
            if pts <= 0:
                continue

            itype = _item_type(sub_types)

            try:
                due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                offset = (due_dt - collected_at).days
            except (ValueError, AttributeError):
                offset = 3

            status = _offset_to_status(offset)
            key = _item_key(itype, title, course)

            if key in seen:
                continue
            seen.add(key)

            items.append({
                "item_id":        key,
                "contributor":    contributor,
                "type":           itype,
                "title":          title,
                "course":         course,
                "due_offset_days": offset,
                "points":         pts,
                "status":         status,
                "source":         f"collab:{path.name}",
            })

    return items


def main() -> None:
    p = argparse.ArgumentParser(description="Convert collab Canvas snapshots to canvas_items format.")
    p.add_argument("--input", required=True,
                   help="Path to JSONL file or directory of JSONL files from share_my_canvas.py")
    p.add_argument("--output", default="data/canvas_items_collab.jsonl",
                   help="Output JSONL path (default: data/canvas_items_collab.jsonl)")
    p.add_argument("--dedupe-against", default=None,
                   help="Existing canvas_items JSONL to deduplicate against (e.g. data/canvas_items_v4.jsonl)")
    args = p.parse_args()

    seen: set[str] = set()

    if args.dedupe_against:
        dedup_path = Path(args.dedupe_against)
        if dedup_path.exists():
            for line in dedup_path.read_text().splitlines():
                if line.strip():
                    try:
                        seen.add(json.loads(line)["item_id"])
                    except (KeyError, json.JSONDecodeError):
                        pass
            print(f"[dedup] loaded {len(seen)} existing item_ids from {dedup_path}")

    input_path = Path(args.input)
    files = sorted(input_path.glob("*.jsonl")) if input_path.is_dir() else [input_path]

    all_items: list[dict] = []
    for f in files:
        batch = convert_file(f, seen)
        print(f"  {f.name}: {len(batch)} new items")
        all_items.extend(batch)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        for item in all_items:
            fh.write(json.dumps(item) + "\n")

    print(f"\n[wrote] {len(all_items)} items → {out}")


if __name__ == "__main__":
    main()
