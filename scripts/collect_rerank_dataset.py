#!/usr/bin/env python3
"""
Canvas Priority Reranker — Collaborative Dataset Collection
==========================================================
Each teammate runs this locally with their own Canvas API token.
It pulls their real Canvas items, generates pairwise ranking pairs,
and outputs a standardized JSONL file ready for Gemma 2B fine-tuning.

Usage:
    # One-time: add to ~/.zshenv
    #   export CANVAS_TOKEN="your_canvas_token"
    #   export CANVAS_BASE_URL="https://canvas.vt.edu"
    #   source ~/.zshenv

    python3 scripts/collect_rerank_dataset.py generate \
        --output data/collab/{teammate_handle}.jsonl \
        --handle your_handle

    # Merge all teammates' data
    python3 scripts/collect_rerank_dataset.py merge \
        data/collab/*.jsonl --output data/collab/rerank_merged.jsonl

    # Clean + deduplicate
    python3 scripts/collect_rerank_dataset.py clean \
        --input data/collab/rerank_merged.jsonl \
        --output data/collab/rerank_clean.jsonl \
        --output data/collab/rerank_clean.jsonl

The output format is compatible with SFTTrainer and the Gemma 2B fine-tune pipeline.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Canvas API ─────────────────────────────────────────────────────────────────

# Canvas config — read from ~/.zshenv (export CANVAS_TOKEN=..., export CANVAS_BASE_URL=...)
# Works out of the box if teammate has added these to ~/.zshenv
TOKEN_FILE = Path.home() / ".canvas_token"  # legacy fallback
CANVAS_API = Path.home() / ".openclaw/hooks/canvas-api.sh"

CANVAS_COURSE_IDS = {
    224083: "CS2505",
    224154: "CS3704",
    224198: "CS3724",
    225576: "HD3114",
    226986: "NEUR2464",
    223306: "BMES2004",
}


def canvas_cmd(subcmd: str, *args, timeout: int = 30) -> list[dict] | None:
    """Call canvas-api.sh hook and return parsed JSON."""
    cmd = [str(CANVAS_API), subcmd] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"[WARN] canvas-api {subcmd} failed: {result.stderr[:200]}")
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[WARN] canvas-api {subcmd} error: {e}")
        return None


def get_token() -> str | None:
    """Get Canvas API token.
    Primary: CANVAS_TOKEN env var (set in ~/.zshenv)
    Fallback: CANVAS_API_TOKEN env var (CI/automation)
    Legacy: ~/.canvas_token file
    """
    # Preferred: CANVAS_TOKEN from ~/.zshenv
    token = os.environ.get("CANVAS_TOKEN")
    if token:
        return token
    # Fallback: CANVAS_API_TOKEN (CI setups)
    token = os.environ.get("CANVAS_API_TOKEN")
    if token:
        return token
    # Legacy fallback
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def save_token(token: str) -> None:
    """Save token to ~/.canvas_token (mode 600)."""
    # Write to ~/.zshenv (primary) and also ~/.canvas_token (legacy fallback)
    zshenv = Path.home() / ".zshenv"
    existing = zshenv.read_text() if zshenv.exists() else ""
    # Remove old CANVAS_TOKEN lines if present
    lines = [l for l in existing.splitlines() if not l.startswith("export CANVAS_TOKEN=")]
    lines.append(f'export CANVAS_TOKEN="{token}"')
    lines.append('export CANVAS_BASE_URL="https://canvas.vt.edu"')
    zshenv.write_text("\n".join(lines) + "\n")
    print("[OK] Token written to ~/.zshenv")
    # Also legacy fallback
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    print(f"[OK] Token also saved to {TOKEN_FILE} (legacy)")


# ── Urgency Signal Computation ───────────────────────────────────────────────────

W_TIME = 3.0
W_TYPE = 2.5
W_POINTS = 1.5
W_STATUS = 2.0
W_GRADE_IMPACT = 2.0

TYPE_SCORES = {
    "exam": 10, "midterm": 9, "final": 9,
    "quiz": 7,
    "assignment": 5, "homework": 5, "hw": 5,
    "project": 6, "phase": 6,
    "lab": 4, "experiment": 4,
    "discussion": 3, "discussion_topic": 3,
    "reading": 2,
    "event": 1, "announcement": 0,
}

STATUS_SCORES = {
    "missing": 15, "late": 7, "none": 0, "submitted": -60, "excused": -60,
}


def _score_type(ptype: str) -> float:
    ptype = ptype.lower()
    for key, score in TYPE_SCORES.items():
        if key in ptype:
            return score
    return 1.0


def _score_status(has_submitted: bool, submitted_at: str | None) -> float:
    if has_submitted:
        return STATUS_SCORES["submitted"]
    return STATUS_SCORES["none"]


def _hours_until(due_at: str) -> float:
    if not due_at:
        return 999.0
    try:
        due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (due - now).total_seconds() / 3600.0
    except:
        return 999.0


def _time_factor(hours: float) -> float:
    """Time urgency — overdue = very high, imminent = high, distant = low."""
    if hours < 0:
        return max(0, 30 + hours * 0.5)  # overdue: decays slowly
    if hours < 6:
        return 25 + (6 - hours) * 2  # within 6h: up to 37
    if hours < 24:
        return 20 + (24 - hours) * 0.5  # within 24h: 20-29
    if hours < 48:
        return 15 + (48 - hours) * 0.25  # within 48h: 15-19
    return max(0, 15 - hours * 0.05)  # beyond 48h: decays slowly


def compute_urgency(item: dict) -> float:
    due_at = item.get("due_at", "") or ""
    hours = _hours_until(due_at)
    ptype = item.get("type", item.get("submission_types", ["assignment"])[0]
                     if item.get("submission_types") else "assignment")
    pts = float(item.get("points_possible", 0) or 0)
    has_sub = item.get("has_submitted_submissions", False)

    return (
        W_TIME * _time_factor(hours) +
        W_TYPE * _score_type(ptype) +
        W_POINTS * min(8.0, pts / 25.0) +
        W_STATUS * _score_status(has_sub, None) +
        W_GRADE_IMPACT * 5.0  # default grade impact; teammates can override
    )


# ── Item Serialization ─────────────────────────────────────────────────────────

DUE_LABELS = [
    (0.5, "< 30m"),
    (1, "< 1h"),
    (2, "< 2h"),
    (4, "< 4h"),
    (8, "< 8h"),
    (24, "Today"),
    (48, "Tomorrow"),
    (72, "< 3d"),
    (168, "< 1w"),
]


def _due_label(hours: float) -> str:
    if hours < 0:
        return f"Overdue {abs(hours):.0f}h"
    for threshold, label in DUE_LABELS:
        if hours < threshold:
            return label
    days = hours / 24
    if days < 14:
        return f"{days:.0f}d"
    return "2w+"


TYPE_BADGES = {
    "exam": "[EXAM]", "midterm": "[EXAM]", "final": "[EXAM]",
    "quiz": "[QUIZ]",
    "assignment": "[ASGN]", "homework": "[ASGN]", "hw": "[ASGN]",
    "project": "[PROJ]", "phase": "[PROJ]",
    "lab": "[LAB]",
    "discussion": "[DISC]", "discussion_topic": "[DISC]",
    "reading": "[READ]",
    "event": "[EVNT]", "announcement": "[EVNT]",
}


def _type_badge(ptype: str) -> str:
    ptype = ptype.lower()
    for key, badge in TYPE_BADGES.items():
        if key in ptype:
            return badge
    return "[ASGN]"


def serialize_item(item: dict) -> str:
    due_at = item.get("due_at", "") or ""
    hours = _hours_until(due_at)
    due_lbl = _due_label(hours)
    ptype = item.get("type", "assignment")
    badge = _type_badge(ptype)
    title = item.get("name", item.get("title", "Unknown"))[:50]
    course = CANVAS_COURSE_IDS.get(item.get("course_id", 0), str(item.get("course_id", "")))
    pts = item.get("points_possible", 0) or 0
    has_sub = item.get("has_submitted_submissions", False)
    status = "DONE" if has_sub else ("MISSING" if hours < 0 else "OPEN")

    return f"{badge} {title} — {course} — {due_lbl} — {pts:.0f}pts — {status}"


# ── Pair Generation ───────────────────────────────────────────────────────────

QUERY_TEMPLATES = [
    "What's due right now?",
    "What's the most urgent?",
    "What should I do first?",
    "What has the biggest impact on my grade?",
    "What's due today?",
    "What's due this week?",
    "What can I skip if I'm running out of time?",
    "What hasn't been submitted yet?",
    "What matters most for {course}?",
    "What's overdue?",
    "What's the highest-value assignment?",
    "What quiz or exam should I prioritize?",
    "What's closing soon?",
    "What did I forget about?",
    "What needs the most attention?",
    "What assignment is worth the most points?",
    "What can I finish quickly?",
]


@dataclass
class RankingPair:
    id: str
    query: str
    item_a: dict
    item_b: dict
    preference: int  # 1 = A is more urgent, 0 = B is more urgent
    urgency_a: float
    urgency_b: float
    reason: str
    pair_type: str
    source_user: str
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RankingPair":
        return cls(
            id=d["id"],
            query=d["query"],
            item_a=d["item_a"],
            item_b=d["item_b"],
            preference=d["preference"],
            urgency_a=d["urgency_a"],
            urgency_b=d["urgency_b"],
            reason=d["reason"],
            pair_type=d["pair_type"],
            source_user=d["source_user"],
            signals=d.get("signals", []),
        )


def _signal_reason(urgency_a: float, urgency_b: float,
                   item_a: dict, item_b: dict) -> tuple[str, list[str]]:
    signals = []
    reasons = []
    ha = _hours_until(item_a.get("due_at", "") or "")
    hb = _hours_until(item_b.get("due_at", "") or "")
    pa = _score_type(item_a.get("type", ""))
    pb = _score_type(item_b.get("type", ""))
    sa = _score_status(item_a.get("has_submitted_submissions", False), None)
    sb = _score_status(item_b.get("has_submitted_submissions", False), None)

    if abs(ha - hb) > 4:
        who = "A" if ha < hb else "B"
        reasons.append(f"{who} is due sooner")
        signals.append("time_ordering")
    if abs(pa - pb) >= 2:
        who = "A" if pa > pb else "B"
        reasons.append(f"{who} is a higher-stakes item type")
        signals.append("type_weight")
    if abs(sa - sb) >= 5:
        who = "A" if sa > sb else "B"
        reasons.append(f"{who} is still {['OPEN','MISSING'][sa>sb]}")
        signals.append("submission_status")
    pts_a = float(item_a.get("points_possible", 0) or 0)
    pts_b = float(item_b.get("points_possible", 0) or 0)
    if abs(pts_a - pts_b) >= 25:
        who = "A" if pts_a > pts_b else "B"
        reasons.append(f"{who} is worth more points ({max(pts_a,pts_b):.0f} vs {min(pts_a,pts_b):.0f})")
        signals.append("points_weight")

    if not reasons:
        reasons.append("A has slightly more urgency overall")
        signals.append("marginal_difference")

    return " ".join(reasons), signals


def generate_pairs(items: list[dict], user_handle: str,
                   min_diff: float = 3.0,
                   include_hard_negatives: bool = True,
                   max_pairs: int = 2000) -> list[RankingPair]:
    """
    Generate pairwise ranking pairs from a list of Canvas items.

    Args:
        items: Canvas assignment/quiz items with due_at, type, points_possible, etc.
        user_handle: Teammate's identifier (for deduplication in merged dataset)
        min_diff: Minimum urgency difference (>= this = clear preference, < this = hard negative)
        include_hard_negatives: Include pairs where urgency difference is small
        max_pairs: Stop generating after this many pairs

    Returns:
        List of RankingPair objects
    """
    # Compute urgency for each item
    for item in items:
        item["_urgency"] = compute_urgency(item)
        item["_hours"] = _hours_until(item.get("due_at", "") or "")

    pairs = []
    pair_keys = set()

    # Sort by urgency
    sorted_items = sorted(items, key=lambda x: x["_urgency"], reverse=True)

    for i, item_a in enumerate(sorted_items):
        for item_b in sorted_items[i + 1:]:
            if len(pairs) >= max_pairs:
                break

            diff = abs(item_a["_urgency"] - item_b["_urgency"])
            is_hard_negative = diff < min_diff
            if is_hard_negative and not include_hard_negatives:
                continue

            # Determine preference — randomly assign winner to create balanced dataset
            # item_a is higher urgency (sorted desc), but we flip coin to assign preference
            import random
            preference = 1 if random.random() < 0.5 else 0
            if preference == 1:
                winner_i, loser_i = item_a, item_b
            else:
                winner_i, loser_i = item_b, item_a
            reason, signals = _signal_reason(
                item_a["_urgency"], item_b["_urgency"], item_a, item_b
            )

            pair_type = "hard_negative" if is_hard_negative else "standard"

            pair_key = hashlib.md5(
                f"{item_a.get('id','x')}-{item_b.get('id','y')}".encode()
            ).hexdigest()[:12]
            if pair_key in pair_keys:
                continue
            pair_keys.add(pair_key)

            query = QUERY_TEMPLATES[len(pairs) % len(QUERY_TEMPLATES)]

            pair = RankingPair(
                id=f"{user_handle}-{pair_key}",
                query=query,
                item_a={"name": item_a.get("name","?"), "course_id": item_a.get("course_id"),
                        "due_at": item_a.get("due_at"), "type": item_a.get("type"),
                        "points_possible": item_a.get("points_possible"),
                        "has_submitted_submissions": item_a.get("has_submitted_submissions", False),
                        "urgency": item_a["_urgency"],
                        "serialized": serialize_item(item_a)},
                item_b={"name": item_b.get("name","?"), "course_id": item_b.get("course_id"),
                        "due_at": item_b.get("due_at"), "type": item_b.get("type"),
                        "points_possible": item_b.get("points_possible"),
                        "has_submitted_submissions": item_b.get("has_submitted_submissions", False),
                        "urgency": item_b["_urgency"],
                        "serialized": serialize_item(item_b)},
                preference=preference,
                urgency_a=item_a["_urgency"],
                urgency_b=item_b["_urgency"],
                reason=reason,
                pair_type=pair_type,
                source_user=user_handle,
                signals=signals,
            )
            pairs.append(pair)

        if len(pairs) >= max_pairs:
            break

    return pairs


# ── Data Cleaning ──────────────────────────────────────────────────────────────

def load_pairs(path: Path) -> list[dict]:
    """Load JSONL pairs from file."""
    pairs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def deduplicate_pairs(pairs: list[dict]) -> list[dict]:
    """
    Deduplicate pairs by item pair (same two items, regardless of order).
    Keep the one with the longer/more detailed reason.
    """
    seen = {}
    for p in pairs:
        ids_a = p["item_a"].get("id", p["item_a"].get("name", "x"))
        ids_b = p["item_b"].get("id", p["item_b"].get("name", "y"))
        key = tuple(sorted([ids_a, ids_b]))
        if key not in seen:
            seen[key] = p
        else:
            # Keep the one with more signals (more thorough reasoning)
            if len(p.get("signals", [])) > len(seen[key].get("signals", [])):
                seen[key] = p
    return list(seen.values())


def balance_preferences(pairs: list[dict]) -> list[dict]:
    """Balance preference 1 vs 0 to reduce bias."""
    prefs = {1: [], 0: []}
    for p in pairs:
        prefs[p["preference"]].append(p)
    min_count = min(len(prefs[1]), len(prefs[0]))
    balanced = prefs[1][:min_count] + prefs[0][:min_count]
    return balanced


def stats(pairs: list[dict]) -> str:
    if not pairs:
        return "  (empty)"
    pref1 = sum(1 for p in pairs if p["preference"] == 1)
    pref0 = len(pairs) - pref1
    pair_types = {}
    for p in pairs:
        pair_types[p.get("pair_type", "unknown")] = \
            pair_types.get(p.get("pair_type", "unknown"), 0) + 1
    users = set(p.get("source_user", "?") for p in pairs)
    lines = [
        f"  Total pairs: {len(pairs)}",
        f"  Preference 1 (A): {pref1}, Preference 0 (B): {pref0}",
        f"  Pair types: {dict(pair_types)}",
        f"  Contributors: {len(users)} ({', '.join(sorted(users))})",
    ]
    return "\n".join(lines)


# ── SFTTrainer Format ───────────────────────────────────────────────────────────

def format_for_sft(pairs: list[dict]) -> list[dict]:
    """
    Convert pairs to SFTTrainer text format for Gemma 2B causal LM fine-tuning.
    """
    formatted = []
    for p in pairs:
        pref = "A" if p["preference"] == 1 else "B"
        text = (
            f"[Query]: {p['query']}\n"
            f"Item A: {p['item_a']['serialized']}\n"
            f"Item B: {p['item_b']['serialized']}\n"
            f"Which is more urgent? Item {pref} is more urgent.\n"
            f"Reason: {p['reason']}<eos>"
        )
        formatted.append({
            "text": text,
            "id": p["id"],
            "pair_type": p.get("pair_type", "standard"),
            "source_user": p.get("source_user", "unknown"),
        })
    return formatted


# ── Main CLI ───────────────────────────────────────────────────────────────────

def cmd_setup(args):
    token = args.token or os.environ.get("CANVAS_API_TOKEN")
    if not token:
        print("No token provided. Pass --token or set CANVAS_API_TOKEN env var.")
        print("Get your token at: https://canvas.vt.edu/profile/settings")
        sys.exit(1)
    save_token(token)
    # Verify it works
    result = subprocess.run([str(CANVAS_API), "courses"],
                           capture_output=True, text=True, env={**os.environ, "CANVAS_TOKEN": token, "CANVAS_BASE_URL": "https://canvas.vt.edu"})
    if result.returncode == 0:
        print("[OK] Token verified — can access Canvas API")
    else:
        print(f"[WARN] Token may not work: {result.stderr[:200]}")


def cmd_generate(args):
    token = get_token()
    if not token:
        print("[ERROR] No Canvas token. Run: python3 scripts/collect_rerank_dataset.py --setup")
        sys.exit(1)

    # Set token in env for canvas-api.sh
    env = {**os.environ, "CANVAS_API_TOKEN": token}

    items = []
    for course_id, course_code in CANVAS_COURSE_IDS.items():
        course_items = canvas_cmd("assignments", str(course_id), timeout=30)
        if not course_items:
            print(f"[WARN] No items from {course_code} ({course_id})")
            continue
        for item in course_items:
            item["course_id"] = course_id
            item["course_code"] = course_code
        items.extend(course_items)
        print(f"  {course_code}: {len(course_items)} items")

    if not items:
        print("[ERROR] No Canvas items fetched. Check token and API access.")
        sys.exit(1)

    print(f"\n[INFO] Generating up to {args.limit} pairs from {len(items)} items...")
    pairs = generate_pairs(
        items,
        user_handle=args.handle,
        min_diff=args.min_diff,
        include_hard_negatives=not args.no_hard_negatives,
        max_pairs=args.limit,
    )

    # Write JSONL
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair.to_dict()) + "\n")

    print(f"\n[OK] Wrote {len(pairs)} pairs → {out_path}")
    print(stats(pairs))

    # Optional: also write SFTTrainer format
    if args.sft_format:
        sft_path = out_path.with_suffix(".sft.jsonl")
        sft_pairs = format_for_sft(pairs)
        with open(sft_path, "w") as f:
            for p in sft_pairs:
                f.write(json.dumps(p) + "\n")
        print(f"[OK] SFTTrainer format → {sft_path}")


def cmd_merge(args):
    """Merge multiple teammate JSONL files into one."""
    all_pairs = []
    for glob_pattern in args.inputs:
        for path in Path(".").glob(glob_pattern):
            pairs = load_pairs(path)
            print(f"  {path}: {len(pairs)} pairs")
            all_pairs.extend(pairs)

    if not all_pairs:
        print("[ERROR] No pairs loaded")
        sys.exit(1)

    print(f"\n[INFO] Raw merged: {len(all_pairs)} pairs")
    print(stats(all_pairs))

    # Deduplicate
    print("\n[INFO] Deduplicating...")
    deduped = deduplicate_pairs(all_pairs)
    print(f"  After dedup: {len(deduped)} pairs")

    # Balance
    print("\n[INFO] Balancing preferences...")
    balanced = balance_preferences(deduped)
    print(f"  After balance: {len(balanced)} pairs")

    # Write
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for pair in balanced:
            f.write(json.dumps(pair) + "\n")

    print(f"\n[OK] Merged dataset → {out_path}")
    print(stats(balanced))


def cmd_clean(args):
    """Clean and validate a merged dataset."""
    pairs = load_pairs(Path(args.input))
    print(f"[INFO] Loaded: {len(pairs)} pairs")
    print(stats(pairs))

    # Validate required fields
    required = ["id", "query", "item_a", "item_b", "preference", "urgency_a", "urgency_b", "reason"]
    bad = []
    for i, p in enumerate(pairs):
        for field in required:
            if field not in p:
                bad.append(f"  Pair {i}: missing field '{field}'")
    if bad:
        print(f"\n[WARN] {len(bad)} invalid pairs:")
        for b in bad[:5]:
            print(b)

    # Deduplicate
    before = len(pairs)
    pairs = deduplicate_pairs(pairs)
    print(f"\n[INFO] Dedup: {before} → {len(pairs)}")

    # Balance
    before = len(pairs)
    pairs = balance_preferences(pairs)
    print(f"[INFO] Balance: {before} → {len(pairs)}")

    # Write
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")

    print(f"\n[OK] Clean dataset → {out_path}")
    print(stats(pairs))


def cmd_export_sft(args):
    """Export a cleaned dataset to SFTTrainer format."""
    pairs = load_pairs(Path(args.input))
    formatted = format_for_sft(pairs)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for p in formatted:
            f.write(json.dumps(p) + "\n")
    print(f"[OK] Exported {len(formatted)} SFTTrainer examples → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    # --setup
    p_setup = sub.add_parser("setup", help="Save Canvas API token")
    p_setup.add_argument("--token", help="Canvas API token (or set CANVAS_API_TOKEN env var)")

    # --generate
    p_gen = sub.add_parser("generate", help="Generate pairwise ranking pairs from Canvas")
    p_gen.add_argument("--output", "-o", required=True, help="Output JSONL path")
    p_gen.add_argument("--handle", default="teammate",
                      help="Your identifier (e.g. github handle)")
    p_gen.add_argument("--limit", type=int, default=2000, help="Max pairs to generate")
    p_gen.add_argument("--min-diff", type=float, default=3.0,
                      help="Urgency diff threshold — pairs below this are hard negatives")
    p_gen.add_argument("--no-hard-negatives", action="store_true",
                      help="Skip hard negative pairs (near-ties)")

    # --merge
    p_merge = sub.add_parser("merge", help="Merge multiple teammate JSONL files")
    p_merge.add_argument("inputs", nargs="+", help="Input JSONL files (supports globs)")
    p_merge.add_argument("--output", "-o", required=True, help="Output merged JSONL path")

    # --clean
    p_clean = sub.add_parser("clean", help="Clean + validate merged dataset")
    p_clean.add_argument("--input", "-i", required=True, help="Input JSONL")
    p_clean.add_argument("--output", "-o", required=True, help="Output clean JSONL")

    # --export-sft
    p_sft = sub.add_parser("export-sft", help="Export to SFTTrainer text format")
    p_sft.add_argument("--input", "-i", required=True, help="Input clean JSONL")
    p_sft.add_argument("--output", "-o", required=True, help="Output SFTTrainer JSONL")

    args = parser.parse_args()

    if args.cmd == "setup":
        cmd_setup(args)
    elif args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "merge":
        cmd_merge(args)
    elif args.cmd == "clean":
        cmd_clean(args)
    elif args.cmd == "export-sft":
        cmd_export_sft(args)
    else:
        parser.print_help()
