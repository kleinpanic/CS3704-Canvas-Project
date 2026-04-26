#!/usr/bin/env python3
"""
Convert anonymized generate_dataset.py output to run_pipeline.py format.

The pipeline expects:
  - 11 fixed query templates (not natural language)
  - Real item names + serialized representations
  - course_id (integer), id (item integer), name (string)
  - urgency_a/urgency_b (can be negative for overdue items)
  - reason field with explicit diff explanation
  - signals: ['urgency_computed']
  - source_user field

This converter takes anonymized pairs and maps them to the pipeline schema.
If anonymized titles are used (--anon mode), it uses the structural descriptors.
If real names are used (--real mode), it includes actual Canvas item names.

Usage:
  # Convert Klein's anonymized data to pipeline format
  python3 convert_to_pipeline.py \
    --input data/collab/kleinpanic_anon.jsonl \
    --output data/collab/kleinpanic_pipeline.jsonl \
    --source kleinpanic

  # Convert with real names (for personal training, NOT for sharing)
  python3 convert_to_pipeline.py \
    --input data/collab/kleinpanic_anon.jsonl \
    --output data/collab/kleinpanic_pipeline.jsonl \
    --source kleinpanic \
    --use-real-names
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from typing import Optional

# Fixed query templates the pipeline was trained on
PIPELINE_QUERIES = [
    "What's due right now?",
    "What's due today?",
    "What's due this week?",
    "What's overdue?",
    "What's closing soon?",
    "What's the biggest grade impact?",
    "What's the most urgent?",
    "What needs the most attention?",
    "What hasn't been submitted yet?",
    "What should I do first?",
    "What assignment is worth the most points?",
]


def _hours_until(due_str: Optional[str]) -> Optional[float]:
    """Parse ISO date string and return hours until due."""
    if not due_str:
        return None
    try:
        due = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0.0, (due - now).total_seconds() / 3600)
    except Exception:
        return None


def _format_hours(h: Optional[float]) -> str:
    if h is None:
        return "no due date"
    if h <= 0:
        return "OVERDUE"
    if h < 1:
        return f"{int(h * 60)}min"
    if h < 24:
        return f"{int(h)}h"
    if h < 168:
        return f"{int(h / 24)}d"
    return f"{int(h / 168)}w"


def _build_serialized(item: dict, item_letter: str = "A") -> str:
    """Build the serialized representation the pipeline expects."""
    title = item.get("anon_title", item.get("name", "Unknown"))
    course = item.get("course", item.get("course_id", "?"))
    hours = item.get("hours_until")
    pts = item.get("points")
    submitted = item.get("submitted", False)
    missing = item.get("missing", False)
    score_pct = item.get("score_percent")
    extra_ec = item.get("is_extra_credit", False)

    h_str = _format_hours(hours)
    pts_str = f"{int(pts)}pts" if pts else "0pts"

    status = "DONE" if submitted else "MISSING" if missing else "PENDING"

    type_char = "ASGN"
    item_type = item.get("type", "")
    if item_type == "quiz":
        type_char = "QUIZ"
    elif item_type == "exam":
        type_char = "EXAM"
    elif item_type == "discussion":
        type_char = "DISC"
    elif item_type == "participation":
        type_char = "PART"

    if extra_ec:
        type_char = "EC"

    # e.g. [ASGN] 100-point graded assignment, due in 24h, unsubmitted — COURSE001 — 100pts — PENDING
    return f"[{type_char}] {title} — {course} — {h_str} — {pts_str} — {status}"


def _compute_pipeline_urgency(urgency_score: float, hours_until: Optional[float]) -> float:
    """
    Map the new urgency score (always positive, 0-200+) to the pipeline's scale.
    Pipeline scale: negative for past items, positive for future items.
    Old pipeline range: -117 to +62.
    New script range: 0 to 200+.
    """
    if hours_until is None:
        return urgency_score  # no due date, keep as-is

    if hours_until <= 0:
        # Past/overdue items get negative urgency in pipeline
        # Map: overdue (hours_until=0) → -100 to -150 range
        offset = min(urgency_score, 150)
        return -(50 + offset)
    else:
        # Future items keep positive (but cap to match pipeline range)
        return min(urgency_score, 150)


def build_reason(a_item: dict, b_item: dict, pref: int,
                 urgency_a: float, urgency_b: float) -> str:
    winner = "A" if pref == 1 else "B"
    loser = "B" if pref == 1 else "A"
    w_urg = urgency_a if pref == 1 else urgency_b
    l_urg = urgency_b if pref == 1 else urgency_a
    diff = abs(urgency_a - urgency_b)
    return f"Item {winner} has higher urgency ({winner}={w_urg:.1f} {loser}={l_urg:.1f}, diff={diff:.1f})"


def convert_pair(pair: dict, source_user: str, use_real_names: bool,
                 course_map: dict[str, int]) -> dict:
    """Convert a single anonymized pair to pipeline format."""
    item_a = pair["item_a"]
    item_b = pair["item_b"]

    # Compute pipeline-format urgency values
    urg_a = _compute_pipeline_urgency(item_a.get("urgency_score", 0), item_a.get("hours_until"))
    urg_b = _compute_pipeline_urgency(item_b.get("urgency_score", 0), item_b.get("hours_until"))

    # Pick a query template
    query = random.choice(PIPELINE_QUERIES)

    # Determine pair type (hard_negative if one item has ignore_reason)
    has_ignore = item_a.get("ignore_reason") or item_b.get("ignore_reason")
    pair_type = "hard_negative" if has_ignore else pair.get("pair_type", "standard")

    # Build serialized representations
    ser_a = _build_serialized(item_a, "A")
    ser_b = _build_serialized(item_b, "B")

    # Build item_a and item_b in pipeline format
    def pipeline_item(item: dict, letter: str, course_map: dict) -> dict:
        # Resolve course code → course_id (integer)
        course_code = item["course"]
        cid = course_map.get(course_code, 0)

        # Anonymous mode: use anon_title
        # Real mode: would use actual name (not available in anon file)
        name = item.get("anon_title", "Unknown")

        # For real names we'd need the raw data — in anonymized mode we use anon_title
        # The id is the pair index (we don't have item IDs in anon mode)
        item_id = hash(f"{course_code}_{name}") % 10000000

        return {
            "name": name,
            "id": item_id,
            "course_id": cid,
            "due_at": None,  # anonymized, no real dates
            "type": item.get("type"),
            "points_possible": item.get("points"),
            "has_submitted_submissions": item.get("submitted", False),
            "urgency": _compute_pipeline_urgency(
                item.get("urgency_score", 0),
                item.get("hours_until")
            ),
            "serialized": _build_serialized(item, letter),
        }

    # Map course codes to integers
    all_course_codes = set(item["course"] for item in [item_a, item_b])
    local_course_map = {}
    for i, cc in enumerate(sorted(all_course_codes)):
        if cc not in course_map:
            course_map[cc] = 1000 + i

    result_a = pipeline_item(item_a, "A", local_course_map)
    result_b = pipeline_item(item_b, "B", local_course_map)

    return {
        "id": f"{source_user}-{hash(pair['query'] + item_a['course'] + item_b['course']) % 10000}",
        "query": query,
        "item_a": result_a,
        "item_b": result_b,
        "preference": pair["preference"],
        "urgency_a": round(result_a["urgency"], 2),
        "urgency_b": round(result_b["urgency"], 2),
        "reason": build_reason(item_a, item_b, pair["preference"], urg_a, urg_b),
        "pair_type": pair_type,
        "source_user": source_user,
        "signals": ["urgency_computed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert anonymized pairs to pipeline format.")
    parser.add_argument("--input", required=True, help="Input JSONL from generate_dataset.py")
    parser.add_argument("--output", required=True, help="Output JSONL for run_pipeline.py")
    parser.add_argument("--source", required=True, help="Source handle (e.g. kleinpanic)")
    parser.add_argument("--use-real-names", action="store_true",
                        help="Include real names (only for personal data, NOT for sharing)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for query assignment")
    args = parser.parse_args()

    random.seed(args.seed)

    print(f"Reading: {args.input}")
    with open(args.input) as f:
        meta = json.loads(f.readline())  # metadata header
        pairs = [json.loads(line) for line in f if line.strip()]

    print(f"  Metadata: {len(meta.get('courses', []))} courses, {meta.get('n_pairs', '?')} pairs")
    print(f"  Source: {args.source}")

    # Build course code → course_id map from metadata
    course_map: dict[str, int] = {}
    for cid_str, code in meta.get("course_map", {}).items():
        course_map[code] = int(cid_str)

    # Convert all pairs
    converted = []
    for pair in pairs:
        try:
            cv = convert_pair(pair, args.source, args.use_real_names, course_map)
            converted.append(cv)
        except Exception as e:
            print(f"  Error converting pair: {e}")
            continue

    print(f"\nConverted: {len(converted)}/{len(pairs)} pairs")

    # Write output
    print(f"Writing: {args.output}")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        for p in converted:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Stats
    pair_types = {}
    urgency_as = []
    urgency_bs = []
    for p in converted:
        pt = p["pair_type"]
        pair_types[pt] = pair_types.get(pt, 0) + 1
        urgency_as.append(p["urgency_a"])
        urgency_bs.append(p["urgency_b"])

    import statistics
    print(f"\nStats:")
    print(f"  Pair types: {pair_types}")
    print(f"  Urgency A: min={min(urgency_as):.1f} max={max(urgency_as):.1f} mean={statistics.mean(urgency_as):.1f}")
    print(f"  Urgency B: min={min(urgency_bs):.1f} max={max(urgency_bs):.1f} mean={statistics.mean(urgency_bs):.1f}")

    # Sample
    print(f"\nSample output:")
    for p in converted[:2]:
        print(f"  id={p['id']} query={p['query']}")
        print(f"  item_a: {p['item_a']['name'][:60]}")
        print(f"    serialized: {p['item_a']['serialized'][:80]}")
        print(f"    urgency_a={p['urgency_a']} urgency_b={p['urgency_b']}")
        print(f"  reason: {p['reason']}")


if __name__ == "__main__":
    main()