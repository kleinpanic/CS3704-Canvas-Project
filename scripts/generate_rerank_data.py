#!/usr/bin/env python3
"""
Canvas Item Reranker — Training Data Generator.

Generates pairwise ranking training data from Canvas item history.
Used to fine-tune a small reranker model (Gemma 4B or similar)
for ordering Canvas items by urgency/priority.

Usage:
    python scripts/generate_rerank_data.py [--limit N] [--output data/rerank_train.jsonl]

Output format (JSONL — one example per line):
    {
        "query": str,          # e.g. "due soon", "check grades", "all"
        "item_a": str,         # serialized item A (title, type, due, course, points)
        "item_b": str,         # serialized item B
        "preference": int,     # 1 if A should rank higher than B, 0 otherwise
        "urgency_a": float,    # computed urgency score A
        "urgency_b": float,    # computed urgency score B
        "reason": str          # human-readable reason for preference
    }

Urgency score formula:
    urgency = base_score + time_score + status_score + type_score + points_score

Where:
    base_score     = 0.0 (already overdue gets +20)
    time_score     = max(0, (72 - hours_until_due))  for future items
                   = (hours_overdue - 0) * 2  for overdue items
    status_score   = missing:+10, late:+5, submitted:-50, excused:-50
    type_score     = exam:+8, quiz:+6, assignment:+4, discussion:+2, event:+1, announcement:+0
    points_score   = min(6, points / 50)   (capped at 6)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

# ── Urgency scoring ────────────────────────────────────────────────────────────

_TYPE_SCORES = {
    "exam": 8,
    "quiz": 6,
    "assignment": 4,
    "discussion": 2,
    "event": 1,
    "announcement": 0,
    "submission": 0,
}

_STATUS_SCORES = {
    "missing": 10,
    "late": 5,
    "submitted": -50,
    "excused": -50,
}


def parse_due_iso(due_iso: str, tz: str = "America/New_York") -> dt.datetime | None:
    """Parse ISO date string to datetime."""
    if not due_iso:
        return None
    try:
        # Handle Z suffix and various formats
        iso_clean = due_iso.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(iso_clean.replace(" ", "T"))
    except Exception:
        return None


def compute_urgency(
    item: dict[str, Any],
    now: dt.datetime | None = None,
    tz: str = "America/New_York",
) -> float:
    """Compute urgency score for a Canvas item.

    Higher score = more urgent = should rank higher.
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    score = 0.0

    # ── Status flags ──────────────────────────────────────────────────────
    flags = item.get("status_flags", [])
    for flag in flags:
        flag_lower = flag.lower()
        if flag_lower in _STATUS_SCORES:
            score += _STATUS_SCORES[flag_lower]
        elif "late" in flag_lower:
            score += _STATUS_SCORES["late"]

    # ── Type score ──────────────────────────────────────────────────────
    ptype = item.get("ptype", "").lower()
    for t, s in _TYPE_SCORES.items():
        if t in ptype:
            score += s
            break

    # ── Points score (max +6) ───────────────────────────────────────────
    points = item.get("points") or item.get("points_possible") or 0
    try:
        score += min(6.0, float(points) / 50.0)
    except (TypeError, ValueError):
        pass

    # ── Time score ─────────────────────────────────────────────────────
    due_iso = item.get("due_iso", "")
    due_dt = parse_due_iso(due_iso)
    if due_dt:
        try:
            # Ensure timezone awareness for comparison
            due_utc = due_dt.astimezone(dt.timezone.utc)
            delta_h = (due_utc - now).total_seconds() / 3600.0

            if delta_h < 0:
                # Overdue: urgency grows with how overdue
                score += max(20, abs(delta_h) * 2)
            elif delta_h < 168:  # within 1 week
                score += max(0, (168 - delta_h) / 24) * 2  # ~2 pts per day
            # > 1 week out: no time bonus
        except Exception:
            pass

    return max(0.0, score)


def serialize_item(item: dict[str, Any]) -> str:
    """Serialize a Canvas item to a short readable string."""
    parts = []

    # Type badge
    ptype = item.get("ptype", "?")
    type_map = {"assignment": "ASGN", "quiz": "QUIZ", "exam": "EXAM",
               "discussion": "DISC", "event": "EVNT", "announcement": "NOTE"}
    badge = type_map.get(ptype.lower(), ptype[:4].upper())
    parts.append(f"[{badge}]")

    # Title (truncated)
    title = (item.get("title") or "(untitled)")[:40]
    parts.append(title)

    # Course code
    code = item.get("course_code", "")
    if code:
        parts.append(f"@{code}")

    # Due date
    due_iso = item.get("due_iso", "")
    due_dt = parse_due_iso(due_iso)
    if due_dt:
        due_str = due_dt.strftime("%m/%d %H:%M")
        delta_h = (due_dt.astimezone(dt.timezone.utc) - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600.0
        if delta_h < 0:
            parts.append(f"OVERDUE")
        elif delta_h < 24:
            parts.append(f"Today")
        elif delta_h < 48:
            parts.append(f"Tomorrow")
        else:
            parts.append(f"Due {due_str}")

    # Points
    points = item.get("points") or item.get("points_possible") or 0
    if points:
        parts.append(f"{points:.0f}pts")

    # Status flags
    flags = item.get("status_flags", [])
    if "missing" in " ".join(flags).lower():
        parts.append("MISSING")
    elif "late" in " ".join(flags).lower():
        parts.append("LATE")

    return " ".join(parts)


def _rank_score(item: dict[str, Any]) -> float:
    """Alias for compute_urgency — used in sorting."""
    return compute_urgency(item)


def generate_pairs(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Generate pairwise ranking examples from a list of items.

    For N items, generates O(N²) pairs but only where preference is clear.
    """
    pairs = []
    scored = [(compute_urgency(it), it) for it in items]
    scored.sort(key=lambda x: -x[0])  # descending urgency

    seen = set()
    for i, (score_a, item_a) in enumerate(scored):
        for score_b, item_b in scored[i + 1:]:
            # Create stable pair key
            key_a = item_a.get("key", item_a.get("plannable_id", i))
            key_b = item_b.get("key", item_b.get("plannable_id", i))
            pair_key = (min(key_a, key_b), max(key_a, key_b))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            preference = 1 if score_a >= score_b else 0
            reason = _explain_preference(item_a, item_b, score_a, score_b)

            pairs.append({
                "query": query,
                "item_a": serialize_item(item_a),
                "item_b": serialize_item(item_b),
                "preference": preference,
                "urgency_a": round(score_a, 2),
                "urgency_b": round(score_b, 2),
                "reason": reason,
            })

    return pairs


def _explain_preference(item_a: dict, item_b: dict, score_a: float, score_b: float) -> str:
    """Generate a human-readable explanation for the pair preference."""
    reasons = []
    delta = abs(score_a - score_b)

    # Status
    flags_a = " ".join(item_a.get("status_flags", []))
    flags_b = " ".join(item_b.get("status_flags", []))
    if "missing" in flags_a.lower() and "missing" not in flags_b.lower():
        reasons.append("A is missing")
    elif "missing" in flags_b.lower() and "missing" not in flags_a.lower():
        reasons.append("B is missing")
    elif "late" in flags_a.lower() and "late" not in flags_b.lower():
        reasons.append("A is late")
    elif "late" in flags_b.lower() and "late" not in flags_a.lower():
        reasons.append("B is late")

    # Due time
    now = dt.datetime.now(dt.timezone.utc)
    due_a = parse_due_iso(item_a.get("due_iso", ""))
    due_b = parse_due_iso(item_b.get("due_iso", ""))
    if due_a and due_b:
        delta_h_a = (due_a.astimezone(dt.timezone.utc) - now).total_seconds() / 3600.0
        delta_h_b = (due_b.astimezone(dt.timezone.utc) - now).total_seconds() / 3600.0
        if delta_h_a < delta_h_b:
            reasons.append("A is due sooner")
        else:
            reasons.append("B is due sooner")

    # Points
    pts_a = float(item_a.get("points") or item_a.get("points_possible") or 0)
    pts_b = float(item_b.get("points") or item_b.get("points_possible") or 0)
    if pts_a > pts_b:
        reasons.append("A is worth more points")
    elif pts_b > pts_a:
        reasons.append("B is worth more points")

    if not reasons:
        reasons.append(f"Urgency score {score_a:.1f} vs {score_b:.1f}")
    return "; ".join(reasons[:2])


# ── Sample data generator (when no live Canvas connection) ──────────────────

SAMPLE_ITEMS = [
    # Overdue, missing assignment
    {
        "key": "sample_001",
        "ptype": "assignment",
        "title": "CS 3704 Problem Set 3 — Graph Algorithms",
        "course_code": "CS 3704",
        "due_iso": "2026-04-10T23:59:00Z",
        "points": 100.0,
        "status_flags": ["missing"],
    },
    # Overdue, late quiz
    {
        "key": "sample_002",
        "ptype": "quiz",
        "title": "NEUR 2464 Neuroimaging Quiz 2",
        "course_code": "NEUR 2464",
        "due_iso": "2026-04-11T22:00:00Z",
        "points": 25.0,
        "status_flags": ["late"],
    },
    # Due today, assignment
    {
        "key": "sample_003",
        "ptype": "assignment",
        "title": "HD 3114 Reading Response Week 12",
        "course_code": "HD 3114",
        "due_iso": "2026-04-14T23:59:00Z",
        "points": 15.0,
        "status_flags": [],
    },
    # Due tomorrow, high-value exam
    {
        "key": "sample_004",
        "ptype": "exam",
        "title": "CS 2505 Midterm 2 — C Programming",
        "course_code": "CS 2505",
        "due_iso": "2026-04-15T23:59:00Z",
        "points": 200.0,
        "status_flags": [],
    },
    # Due in 3 days, discussion
    {
        "key": "sample_005",
        "ptype": "discussion",
        "title": "NEUR 2464 Brain Connectivity Discussion",
        "course_code": "NEUR 2464",
        "due_iso": "2026-04-17T23:59:00Z",
        "points": 10.0,
        "status_flags": [],
    },
    # Due in 1 week, event (low urgency)
    {
        "key": "sample_006",
        "ptype": "event",
        "title": "VT Spring Career Fair",
        "course_code": "VT",
        "due_iso": "2026-04-21T09:00:00Z",
        "points": 0.0,
        "status_flags": [],
    },
    # Already submitted
    {
        "key": "sample_007",
        "ptype": "assignment",
        "title": "CS 3704 Lab 4 — SQL Queries",
        "course_code": "CS 3704",
        "due_iso": "2026-04-08T23:59:00Z",
        "points": 50.0,
        "status_flags": ["submitted"],
    },
    # Due in 5 days, high-weight assignment
    {
        "key": "sample_008",
        "ptype": "assignment",
        "title": "HD 3114 Research Summary Draft",
        "course_code": "HD 3114",
        "due_iso": "2026-04-19T23:59:00Z",
        "points": 200.0,
        "status_flags": [],
    },
    # Due in 2 days, announcement (low type score)
    {
        "key": "sample_009",
        "ptype": "announcement",
        "title": "CS 3704 Final Project Guidelines Posted",
        "course_code": "CS 3704",
        "due_iso": "2026-04-16T12:00:00Z",
        "points": 0.0,
        "status_flags": [],
    },
    # Due in 4 days, medium points
    {
        "key": "sample_010",
        "ptype": "quiz",
        "title": "NEUR 2464 fMRI Analysis Quiz",
        "course_code": "NEUR 2464",
        "due_iso": "2026-04-18T22:00:00Z",
        "points": 30.0,
        "status_flags": [],
    },
]


QUERIES = [
    "due soon",
    "check my grades",
    "what's due today",
    "all items",
    "upcoming assignments",
    "high priority",
    "exams and quizzes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reranker training data from Canvas items")
    parser.add_argument("--output", "-o", default="data/rerank_train.jsonl", help="Output JSONL path")
    parser.add_argument("--limit", "-n", type=int, default=500, help="Max pairs to generate")
    parser.add_argument("--sample", action="store_true", help="Use sample items instead of Canvas API")
    parser.add_argument("--api-url", help="Canvas API base URL")
    parser.add_argument("--token", help="Canvas API token")
    args = parser.parse_args()

    items = SAMPLE_ITEMS
    if not args.sample:
        # Would fetch from Canvas API here
        print("[INFO] Using sample data (--sample mode). Pass --api-url and --token for live data.")
        print("[INFO] Sample data contains 10 realistic Canvas items for demo.")

    all_pairs = []

    # Generate pairs for each query type
    for query in QUERIES:
        pairs = generate_pairs(items, query)
        all_pairs.extend(pairs)

    # Also generate query-agnostic pairs (most general signal)
    general_pairs = generate_pairs(items, "all items ranked by urgency")
    all_pairs.extend(general_pairs)

    # Deduplicate by item_a+item_b
    seen = set()
    unique_pairs = []
    for p in all_pairs:
        key = (p["item_a"][:50], p["item_b"][:50])
        if key not in seen:
            seen.add(key)
            unique_pairs.append(p)

    # Apply limit
    unique_pairs = unique_pairs[:args.limit]

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for pair in unique_pairs:
            f.write(json.dumps(pair) + "\n")

    print(f"[OK] Wrote {len(unique_pairs)} training pairs to {output_path}")

    # Summary stats
    prefs = [p["preference"] for p in unique_pairs]
    print(f"[STATS] Preference=1: {sum(prefs)}, Preference=0: {len(prefs)-sum(prefs)}")

    # Show top 3 pairs
    print("\n[SAMPLE PAIRS]")
    for p in unique_pairs[:3]:
        print(f"  Query: {p['query']}")
        print(f"  A: {p['item_a']} (urgency={p['urgency_a']})")
        print(f"  B: {p['item_b']} (urgency={p['urgency_b']})")
        print(f"  Preference: {'A' if p['preference'] else 'B'} — {p['reason']}")
        print()


if __name__ == "__main__":
    main()