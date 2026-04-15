#!/usr/bin/env python3
"""
Canvas Priority Reranker — Collaborative Dataset Collection
==========================================================
Each teammate runs this locally with their own Canvas API token.
Pulls their real Canvas items, generates pairwise ranking pairs,
and outputs a standardized JSONL file ready for Gemma 2B fine-tuning.

PRIVACY: Use --anonymize to strip identifying information before
committing data to a shared repo. See DATASET_README.md for details.

Usage:
    # One-time: add to ~/.zshenv
    #   export CANVAS_TOKEN="your_canvas_token"
    #   export CANVAS_BASE_URL="https://canvas.vt.edu"
    #   source ~/.zshenv

    # Generate (private — stays on your machine)
    python3 scripts/collect_rerank_dataset.py generate \
        --output data/collab/your_handle.jsonl \
        --handle your_handle

    # ANONYMIZE before sharing (REQUIRED for public/contributed datasets)
    python3 scripts/collect_rerank_dataset.py anonymize \
        --input data/collab/your_handle.jsonl \
        --output data/collab/your_handle_anon.jsonl

    # Merge teammates' ANONYMIZED data
    python3 scripts/collect_rerank_dataset.py merge \
        data/collab/*_anon.jsonl \
        --output data/collab/rerank_merged.jsonl

    # Clean + deduplicate
    python3 scripts/collect_rerank_dataset.py clean \
        --input data/collab/rerank_merged.jsonl \
        --output data/collab/rerank_clean.jsonl

    # Export for Gemma 2B training
    python3 scripts/collect_rerank_dataset.py export-sft \
        --input data/collab/rerank_clean.jsonl \
        --output data/rerank_sft.jsonl
"""

import argparse
import hashlib
import json
import os
import random
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
TOKEN_FILE = Path.home() / ".canvas_token"  # legacy fallback
CANVAS_API = Path.home() / ".openclaw/hooks/canvas-api.sh"

# ── Config ─────────────────────────────────────────────────────────────────────

W_TIME = 3.0
W_TYPE = 2.5
W_POINTS = 1.5
W_STATUS = 2.0

CANCELED_TYPES = {"discussion_topic", "quiz", "exam", "midterm", "final"}
COURSE_CODE_OVERRIDES = {}   # can be populated: {course_id: "CS3704"}
CANVAS_COURSE_IDS = {}        # populated by --course flag at runtime

# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class Item:
    id: int
    name: str
    type: str
    due_at: str
    points_possible: float
    has_submitted_submissions: bool
    course_id: int
    course_name: str = ""
    course_code: str = ""
    hours_until_due: float = 999.0
    urgency: float = 0.0

    def serialized(self, anonymize: bool = False) -> str:
        due_lbl = _due_label(self.hours_until_due)
        badge = _type_badge(self.type)
        title = self.name[:50] if self.name else "Unknown"
        if anonymize:
            # Strip identifying course info
            course = self._anon_course()
            title = self._anon_title()
        else:
            course = self.course_code or str(self.course_id)
        pts = self.points_possible or 0
        status = "DONE" if self.has_submitted_submissions else ("MISSING" if self.hours_until_due < 0 else "OPEN")
        return f"{badge} {title} — {course} — {due_lbl} — {pts:.0f}pts — {status}"

    def _anon_course(self) -> str:
        # Map course_id to anonymized COURSE001, COURSE002, etc.
        h = int(hashlib.md5(str(self.course_id).encode()).hexdigest()[:6], 16)
        num = (h % 999) + 1
        return f"COURSE{num:03d}"

    def _anon_title(self) -> str:
        # Replace assignment name with type only
        t = self.type.lower()
        if "homework" in t or "assignment" in t:
            return "Homework"
        if "quiz" in t:
            return "Quiz"
        if "exam" in t or "midterm" in t or "final" in t:
            return "Exam"
        if "project" in t:
            return "Project"
        if "reading" in t:
            return "Reading"
        return "Assignment"


# ── Helper Functions ────────────────────────────────────────────────────────────

def get_token() -> str | None:
    """Get Canvas API token — prefers CANVAS_TOKEN env var (from ~/.zshenv)."""
    token = os.environ.get("CANVAS_TOKEN")
    if token:
        return token
    token = os.environ.get("CANVAS_API_TOKEN")  # CI fallback
    if token:
        return token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def canvas_api(subpath: str) -> list[dict]:
    """Call canvas-api.sh hook. Returns parsed JSON."""
    token = get_token()
    if not token:
        sys.exit("ERROR: Set CANVAS_TOKEN env var (see ~/.zshenv setup)")
    base = os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu")
    result = subprocess.run(
        [str(CANVAS_API), subpath],
        capture_output=True, text=True,
        env={**os.environ, "CANVAS_TOKEN": token, "CANVAS_BASE_URL": base},
    )
    if result.returncode != 0:
        sys.exit(f"Canvas API error: {result.stderr}")
    return json.loads(result.stdout)


def _hours_until(due_iso: str) -> float:
    if not due_iso:
        return 999.0
    try:
        due = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (due - now).total_seconds() / 3600.0
    except Exception:
        return 999.0


def _due_label(hours: float) -> str:
    if hours < 0:
        return f"Overdue {abs(hours):.0f}h"
    if hours < 1:
        return f"<1h"
    if hours < 24:
        return f"{hours:.0f}h"
    if hours < 168:
        return f"{hours / 24:.0f}d"
    return f"{hours / 168:.0f}w"


def _type_weight(item_type: str) -> float:
    t = item_type.lower()
    if any(k in t for k in CANCELED_TYPES):
        return 1.0
    if "homework" in t or "assignment" in t:
        return 0.7
    if "project" in t:
        return 0.5
    if "reading" in t or "note" in t:
        return 0.2
    return 0.4


def _type_badge(item_type: str) -> str:
    t = (item_type or "").lower()
    if any(k in t for k in CANCELED_TYPES):
        return "[!]"
    if "homework" in t or "assignment" in t:
        return "[=]"
    if "project" in t:
        return "[P]"
    if "quiz" in t:
        return "[?]"
    return "[*]"


def _urgency(item: dict) -> float:
    h = item.get("hours_until_due", 999)
    return round(
        W_TIME * (1.0 / max(h, 0.1) ** 0.5)
        + W_TYPE * _type_weight(item.get("type", ""))
        + W_POINTS * (min(float(item.get("points_possible") or 0), 200) / 200.0)
        + W_STATUS * (0.0 if item.get("has_submitted_submissions") else 1.0),
        4,
    )


def serialize_item(item: dict) -> str:
    """Serialize a Canvas item to a compact string representation."""
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


# ── Pair Generation ────────────────────────────────────────────────────────────

QUERY_TEMPLATES = [
    "What's due right now?",
    "What's the most urgent?",
    "What should I do first?",
    "What has the biggest impact on my grade?",
    "What's the highest-priority item?",
    "Which item has the tightest deadline?",
    "Which item am I most likely to lose points on?",
    "What's the most time-sensitive assignment?",
]


def generate_pairs(items: list[dict], handle: str, include_hard_negatives: bool = True) -> list[dict]:
    """Generate pairwise ranking pairs from a list of Canvas items."""
    pairs = []
    submitted = [i for i in items if i.get("has_submitted_submissions")]
    open_items = [i for i in items if not i.get("has_submitted_submissions")]

    signals_map = {i["id"]: i.get("signals", []) for i in items}

    # Sort items by urgency (descending)
    sorted_items = sorted(items, key=lambda x: x["urgency"], reverse=True)

    # Generate pairs: each item vs items ranked below it
    for i, item_a in enumerate(sorted_items):
        for item_b in sorted_items[i + 1:]:
            ua, ub = item_a["urgency"], item_b["urgency"]
            difficulty = abs(ua - ub)

            query = random.choice(QUERY_TEMPLATES)

            # Ground truth: higher urgency = preferred
            preference = 1 if ua >= ub else 0
            reason = (
                f"Item {'A' if preference == 1 else 'B'} has higher urgency "
                f"({'A' if preference == 1 else 'B'}={ua:.1f} vs {'B' if preference == 1 else 'A'}={ub:.1f}, "
                f"diff={difficulty:.1f})"
            )

            pair = {
                "id": str(uuid.uuid4())[:8],
                "query": query,
                "item_a": {k: v for k, v in item_a.items() if not k.startswith("_")},
                "item_b": {k: v for k, v in item_b.items() if not k.startswith("_")},
                "preference": preference,
                "urgency_a": ua,
                "urgency_b": ub,
                "reason": reason,
                "pair_type": "hard_negative" if difficulty < 3.0 else "standard",
                "source_user": handle,
            }
            pairs.append(pair)

    # Balance preferences to 50/50
    prefs = {1: [], 0: []}
    for p in pairs:
        prefs[p["preference"]].append(p)
    min_c = min(len(prefs[1]), len(prefs[0]))
    pairs = prefs[1][:min_c] + prefs[0][:min_c]
    random.shuffle(pairs)

    return pairs


def deduplicate_pairs(pairs: list[dict]) -> list[dict]:
    seen = {}
    out = []
    for p in pairs:
        key = tuple(sorted([str(p["item_a"].get("id", "")), str(p["item_b"].get("id", ""))]))
        if key not in seen or len(p.get("signals", [])) > len(seen.get(key, {}).get("signals", [])):
            seen[key] = p
    return list(seen.values())


def balance_preferences(pairs: list[dict]) -> list[dict]:
    prefs = {1: [], 0: []}
    for p in pairs:
        prefs[p["preference"]].append(p)
    min_c = min(len(prefs[1]), len(prefs[0]))
    balanced = prefs[1][:min_c] + prefs[0][:min_c]
    random.shuffle(balanced)
    return balanced


def format_for_sft(pairs: list[dict], anonymize: bool = False) -> list[dict]:
    """Format pairs for SFTTrainer. If anonymize=True, strips identifying info."""
    formatted = []
    for p in pairs:
        pref = "A" if p["preference"] == 1 else "B"
        item_a_ser = _serialize_item_anon(p["item_a"]) if anonymize else serialize_item(p["item_a"])
        item_b_ser = _serialize_item_anon(p["item_b"]) if anonymize else serialize_item(p["item_b"])
        text = (
            f"[Query]: {p['query']}\n"
            f"Item A: {item_a_ser}\n"
            f"Item B: {item_b_ser}\n"
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


def _serialize_item_anon(item: dict) -> str:
    """Serialize item with anonymized course and title info."""
    hours = item.get("hours_until_due", 999)
    due_lbl = _due_label(hours)
    badge = _type_badge(item.get("type", ""))
    # Anonymized title: just the type
    title = _anon_title(item.get("type", ""))
    # Anonymized course code
    cid = item.get("course_id", 0)
    h = int(hashlib.md5(str(cid).encode()).hexdigest()[:6], 16)
    course = f"COURSE{(h % 999) + 1:03d}"
    pts = item.get("points_possible", 0) or 0
    has_sub = item.get("has_submitted_submissions", False)
    status = "DONE" if has_sub else ("MISSING" if hours < 0 else "OPEN")
    return f"{badge} {title} — {course} — {due_lbl} — {pts:.0f}pts — {status}"


def _anon_title(item_type: str) -> str:
    t = item_type.lower()
    if "homework" in t or "assignment" in t:
        return "Homework"
    if "quiz" in t:
        return "Quiz"
    if any(k in t for k in ["exam", "midterm", "final"]):
        return "Exam"
    if "project" in t:
        return "Project"
    if "reading" in t:
        return "Reading"
    return "Assignment"


def _serialize_merged_item(item: dict, course_map: dict[int, str]) -> str:
    """Serialize item using a course_map for consistent anonymization."""
    hours = item.get("hours_until_due", 999)
    due_lbl = _due_label(hours)
    badge = _type_badge(item.get("type", ""))
    title = _anon_title(item.get("type", ""))
    cid = item.get("course_id", 0)
    course = course_map.get(cid, f"COURSE{cid % 999 + 1:03d}")
    pts = item.get("points_possible", 0) or 0
    has_sub = item.get("has_submitted_submissions", False)
    status = "DONE" if has_sub else ("MISSING" if hours < 0 else "OPEN")
    return f"{badge} {title} — {course} — {due_lbl} — {pts:.0f}pts — {status}"


def anonymize_pairs(pairs: list[dict], output_path: str) -> list[dict]:
    """
    Anonymize a set of pairs for safe publication.
    - Course IDs → COURSE001, COURSE002, etc. (consistent across dataset)
    - Course names → removed entirely
    - Item names/titles → replaced with just the type (Homework, Quiz, etc.)
    - Absolute due dates → removed (relative hours_until_due is kept)
    - Student identifiers → removed
    - source_user → hashed or set to "contributor{N}"
    - pair IDs → new random IDs (not traceable to original)
    """
    # Build consistent course map across all pairs
    all_course_ids = set()
    for p in pairs:
        all_course_ids.add(p["item_a"].get("course_id", 0))
        all_course_ids.add(p["item_b"].get("course_id", 0))

    # Sort for reproducibility
    sorted_ids = sorted(all_course_ids)
    course_map = {cid: f"COURSE{i + 1:03d}" for i, cid in enumerate(sorted_ids)}

    # Count existing contributors for sequential naming
    seen_users = {}
    next_contrib = 1

    anon_pairs = []
    for p in pairs:
        # Map source user to anonymous contributor ID
        orig_user = p.get("source_user", "unknown")
        if orig_user not in seen_users:
            seen_users[orig_user] = f"contributor{next_contrib:03d}"
            next_contrib += 1
        anon_user = seen_users[orig_user]

        # Serialize with course map
        item_a_ser = _serialize_merged_item(p["item_a"], course_map)
        item_b_ser = _serialize_merged_item(p["item_b"], course_map)

        # Build anonymized pair
        anon_pair = {
            "id": str(uuid.uuid4())[:8],   # new random ID
            "query": p["query"],             # queries are generic
            "item_a": {
                "type": p["item_a"].get("type", "assignment"),
                "points_possible": p["item_a"].get("points_possible", 0),
                "has_submitted_submissions": p["item_a"].get("has_submitted_submissions", False),
                "hours_until_due": p["item_a"].get("hours_until_due", 999),
                "course_code": course_map.get(p["item_a"].get("course_id", 0), "COURSE001"),
                "serialized": item_a_ser,
            },
            "item_b": {
                "type": p["item_b"].get("type", "assignment"),
                "points_possible": p["item_b"].get("points_possible", 0),
                "has_submitted_submissions": p["item_b"].get("has_submitted_submissions", False),
                "hours_until_due": p["item_b"].get("hours_until_due", 999),
                "course_code": course_map.get(p["item_b"].get("course_id", 0), "COURSE001"),
                "serialized": item_b_ser,
            },
            "preference": p["preference"],
            "urgency_a": p["urgency_a"],
            "urgency_b": p["urgency_b"],
            "reason": p["reason"],
            "pair_type": p.get("pair_type", "standard"),
            "source_user": anon_user,
            "_anon": True,
        }
        anon_pairs.append(anon_pair)

    # Write to output
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for p in anon_pairs:
            f.write(json.dumps(p) + "\n")

    n_pairs = len(anon_pairs)
    n_courses = len(course_map)
    n_users = len(seen_users)
    print(f"[ANONYMIZE] {n_pairs} pairs, {n_courses} unique courses → COURSE001-COURSE{n_courses:03d}, {n_users} contributors")
    print(f"[ANONYMIZE] Course map saved to {out_path}.course_map.json")
    with open(str(out_path) + ".course_map.json", "w") as f:
        json.dump({str(k): v for k, v in course_map.items()}, f, indent=2)
    return anon_pairs


# ── CLI Commands ────────────────────────────────────────────────────────────────

def cmd_anonymize(args):
    """Anonymize a JSONL file for safe publication."""
    pairs = []
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    print(f"[ANON] Loaded {len(pairs)} pairs from {args.input}")
    anonymize_pairs(pairs, args.output)
    print(f"[ANON] Done. Anonymized file: {args.output}")


def cmd_setup(args):
    """Save Canvas API token to ~/.zshenv and ~/.canvas_token."""
    import urllib.request
    token = args.token or input("Canvas API token: ").strip()
    if not token:
        sys.exit("Token required.")
    # Verify token works
    base = os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu")
    result = subprocess.run(
        [str(CANVAS_API), "courses"],
        capture_output=True, text=True,
        env={**os.environ, "CANVAS_TOKEN": token, "CANVAS_BASE_URL": base},
    )
    if result.returncode != 0:
        sys.exit(f"Token verification failed: {result.stderr[-200:]}")
    # Write to ~/.zshenv (primary) and also ~/.canvas_token (legacy fallback)
    zshenv = Path.home() / ".zshenv"
    existing = zshenv.read_text() if zshenv.exists() else ""
    lines = [l for l in existing.splitlines() if not l.startswith("export CANVAS_TOKEN=")]
    lines.append(f'export CANVAS_TOKEN="{token}"')
    lines.append('export CANVAS_BASE_URL="https://canvas.vt.edu"')
    zshenv.write_text("\n".join(lines) + "\n")
    print(f"[OK] Token written to ~/.zshenv")
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    print(f"[OK] Token also saved to {TOKEN_FILE} (legacy)")


def cmd_generate(args):
    """Pull Canvas items → pairwise ranking dataset."""
    global CANVAS_COURSE_IDS
    print(f"Generating dataset for handle: {args.handle}")
    print(f"Canvas API: {CANVAS_API}")
    token = get_token()
    if not token:
        sys.exit("ERROR: Set CANVAS_TOKEN env var (see ~/.zshenv setup)")

    # Build course_id → course_code mapping from Canvas
    print("\nFetching courses...")
    courses = canvas_api("courses")
    print(f"  Found {len(courses)} courses")
    CANVAS_COURSE_IDS = {}
    for c in courses:
        cid = c.get("id")
        code = COURSE_CODE_OVERRIDES.get(cid) or c.get("course_code", f"COURSE{cid % 999}")
        CANVAS_COURSE_IDS[cid] = code

    if args.courses:
        requested = {cid: CANVAS_COURSE_IDS.get(cid, f"COURSE{cid % 999}")
                     for cid in args.courses}
        CANVAS_COURSE_IDS = {**CANVAS_COURSE_IDS, **requested}

    # Fetch all assignments
    print("\nFetching assignments...")
    all_items = []
    for cid in CANVAS_COURSE_IDS:
        assignments = canvas_api(f"courses/{cid}/assignment_groups")  # fallback
        for a in assignments:
            a["course_id"] = cid
            a["course_name"] = next(
                (c.get("name", "") for c in courses if c.get("id") == cid), ""
            )
        all_items.extend(assignments)

    # Fetch individual assignments
    for cid in CANVAS_COURSE_IDS:
        items = canvas_api(f"courses/{cid}/items")
        for item in items:
            item["course_id"] = cid
            item["course_name"] = next(
                (c.get("name", "") for c in courses if c.get("id") == cid), ""
            )
        all_items.extend(items)

    # Deduplicate by item ID
    seen = {}
    for item in all_items:
        iid = item.get("id")
        if iid and (iid not in seen or len(item.get("submission", {}).get("attachments", [])) > 0):
            seen[iid] = item
    items = list(seen.values())

    # Compute urgency
    for item in items:
        item["hours_until_due"] = _hours_until(item.get("due_at", ""))
        item["urgency"] = _urgency(item)

    print(f"  Total unique items: {len(items)}")

    # Generate pairs
    print(f"\nGenerating pairwise ranking pairs...")
    pairs = generate_pairs(items, args.handle, include_hard_negatives=True)
    print(f"  Generated {len(pairs)} pairs")

    # Balance
    pairs = balance_preferences(deduplicate_pairs(pairs))
    print(f"  After dedup + balance: {len(pairs)} pairs")

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")

    print(f"\nWrote: {out_path} ({out_path.stat().st_size // 1024}KB)")
    print(f"\nNext: python3 scripts/collect_rerank_dataset.py anonymize \\")
    print(f"    --input {args.output} \\")
    print(f"    --output data/collab/{args.handle}_anon.jsonl")


def cmd_merge(args):
    """Merge multiple teammates' JSONL files into one."""
    import glob
    files = []
    for pattern in args.files:
        files.extend(glob.glob(str(pattern)))
    files = sorted(set(files))
    print(f"Merging {len(files)} files...")
    all_pairs = []
    seen = set()
    for f in files:
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                p = json.loads(line)
                key = (str(p.get("id", "")), str(p.get("source_user", "")))
                if key not in seen:
                    seen.add(key)
                    all_pairs.append(p)
    print(f"  Merged: {len(all_pairs)} unique pairs")
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for p in all_pairs:
            f.write(json.dumps(p) + "\n")
    print(f"  Wrote: {out_path}")


def cmd_clean(args):
    """Clean + validate + balance a merged JSONL."""
    pairs = []
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    print(f"Loaded: {len(pairs)} pairs")
    pairs = deduplicate_pairs(pairs)
    print(f"After dedup: {len(pairs)}")
    pairs = balance_preferences(pairs)
    print(f"After balance: {len(pairs)}")
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")
    print(f"Wrote: {out_path}")


def cmd_export_sft(args):
    """Export pairs to SFTTrainer JSONL format."""
    pairs = []
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    formatted = format_for_sft(pairs, anonymize=getattr(args, "anonymize", False))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for p in formatted:
            f.write(json.dumps(p) + "\n")
    print(f"Wrote: {out_path} ({len(formatted)} examples)")


def stats(pairs: list[dict]) -> str:
    if not pairs:
        return "(empty)"
    pref1 = sum(1 for p in pairs if p.get("preference") == 1)
    pt = {}
    for p in pairs:
        pt[p.get("pair_type", "?")] = pt.get(p.get("pair_type", "?"), 0) + 1
    return (f"Total: {len(pairs)} | Pref A: {pref1}, B: {len(pairs) - pref1} "
            f"| HardNeg: {pt.get('hard_negative', 0)} | Types: {pt}")


# ── CLI Parser ─────────────────────────────────────────────────────────────────



def cmd_split(args):
    """Split a clean dataset into train/test sets (stratified by pair_type)."""
    pairs = []
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))

    import random
    random.seed(args.seed)

    # Stratified split: maintain pair_type distribution
    hard_neg = [p for p in pairs if p.get("pair_type") == "hard_negative"]
    standard = [p for p in pairs if p.get("pair_type") != "hard_negative"]

    def split(lst, frac):
        random.shuffle(lst)
        n = max(1, int(len(lst) * frac))
        return lst[:n], lst[n:]

    train_hn, test_hn = split(hard_neg, 1 - args.test_frac)
    train_std, test_std = split(standard, 1 - args.test_frac)

    train = train_hn + train_std
    test = test_hn + test_std
    random.shuffle(train)
    random.shuffle(test)

    print(f"Total: {len(pairs)} | HardNeg: {len(hard_neg)}, Standard: {len(standard)}")
    print(f"Train: {len(train)} ({len(train_hn)} hard_neg, {len(train_std)} standard)")
    print(f"Test:  {len(test)} ({len(test_hn)} hard_neg, {len(test_std)} standard)")

    def write(path, lst):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            for pair in lst:
                f.write(json.dumps(pair) + "\n")
        print(f"  Wrote: {path} ({p.stat().st_size // 1024}KB)")

    write(args.train, train)
    write(args.test, test)
    print(f"\nTrain/test split done. Test set: {args.test}")


def parse_args():
    p = argparse.ArgumentParser(
        description="Canvas Priority Reranker — Collaborative Dataset Collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    setup_p = sub.add_parser("setup", help="Save Canvas API token to ~/.zshenv")
    setup_p.add_argument("--token", help="Canvas API token (prompts if omitted)")
    setup_p.set_defaults(fn=cmd_setup)

    gen_p = sub.add_parser("generate", help="Pull Canvas items → pairwise ranking dataset")
    gen_p.add_argument("--output", required=True, help="Output JSONL path")
    gen_p.add_argument("--handle", required=True, help="Your handle/username")
    gen_p.add_argument("--courses", nargs="+", type=int, help="Specific Canvas course IDs")
    gen_p.set_defaults(fn=cmd_generate)

    merge_p = sub.add_parser("merge", help="Merge multiple teammates' JSONL files")
    merge_p.add_argument("files", nargs="+", help="Input JSONL files (globs OK)")
    merge_p.add_argument("--output", required=True, help="Output merged JSONL")
    merge_p.set_defaults(fn=cmd_merge)

    clean_p = sub.add_parser("clean", help="Deduplicate + balance a merged JSONL")
    clean_p.add_argument("--input", required=True, help="Input JSONL")
    clean_p.add_argument("--output", required=True, help="Output JSONL")
    clean_p.set_defaults(fn=cmd_clean)

    anon_p = sub.add_parser("anonymize", help="Anonymize pairs for safe publication")
    anon_p.add_argument("--input", required=True, help="Input JSONL")
    anon_p.add_argument("--output", required=True, help="Output anonymized JSONL")
    anon_p.set_defaults(fn=cmd_anonymize)

    sft_p = sub.add_parser("export-sft", help="Export to SFTTrainer JSONL format")
    sft_p.add_argument("--input", required=True, help="Input JSONL (cleaned pairs)")
    sft_p.add_argument("--output", required=True, help="Output SFTTrainer JSONL")
    sft_p.add_argument("--anonymize", action="store_true", help="Anonymize during export")
    sft_p.set_defaults(fn=cmd_export_sft)

    split_p = sub.add_parser("split", help="Split into train/test sets (stratified)")
    split_p.add_argument("--input", required=True, help="Input JSONL (cleaned pairs)")
    split_p.add_argument("--train", required=True, help="Output train JSONL")
    split_p.add_argument("--test", required=True, help="Output test JSONL")
    split_p.add_argument("--test-frac", type=float, default=0.1,
                         help="Fraction for test set (default: 0.1)")
    split_p.add_argument("--seed", type=int, default=42, help="Random seed")
    split_p.set_defaults(fn=cmd_split)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    parse_args()
