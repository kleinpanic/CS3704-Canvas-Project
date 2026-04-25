#!/usr/bin/env python3
"""
Production-Grade Canvas Item Reranker — Training Data Generator.

Generates pairwise ranking training data from live Canvas API + synthetic anchors.
Used to fine-tune a small reranker model (Gemma 4B or similar) for ordering
Canvas items by multi-dimensional urgency.

Usage:
    # Sample mode (no Canvas needed):
    python scripts/generate_rerank_data.py --sample

    # Live Canvas mode (all current semester courses):
    python scripts/generate_rerank_data.py --live --output data/rerank_train.jsonl --limit 1500

Output format (JSONL — one example per line):
    {
        "query": str,          # e.g. "what's due today", "highest value assignments"
        "item_a": dict(title, type, course, due_iso, points, status, grade_impact, serialized),
        "item_b": dict(...),
        "preference": 1 | 0 | -1,  # A preferred | B preferred | tie
        "urgency_a": float,
        "urgency_b": float,
        "reason": str,         # detailed natural-language explanation
        "pair_type": str,      # standard | equivalence | contrast | same-course | cross-course
        "difficulty": str,     # easy | medium | hard  (hard = subtle urgency diff, within 5 pts)
        "signals": [str]       # which self-supervised signals fired
    }

Urgency formula:
    urgency = w1*time_factor + w2*type_factor + w3*points_factor + w4*status_factor + w5*grade_impact

Signals:
    - time_ordering: A due before B, neither has special status → A > B
    - type_hierarchy: exam > quiz > assignment > discussion > event > announcement
    - points_ordering: same type, higher points → higher rank
    - status_ordering: missing > late > none > submitted > excused
    - grade_impact: higher grade-impact items ranked above lower
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── Weights ────────────────────────────────────────────────────────────────────
W_TIME = 3.0
W_TYPE = 2.5
W_POINTS = 1.5
W_STATUS = 2.0
W_GRADE_IMPACT = 2.0

# ── Type hierarchy ─────────────────────────────────────────────────────────────
_TYPE_SCORES = {
    "exam": 10, "quiz": 7, "assignment": 5, "discussion": 3,
    "event": 1, "announcement": 0, "submission": 0, "page": 0, "module": 0,
}

# ── Status hierarchy ───────────────────────────────────────────────────────────
_STATUS_SCORES = {"missing": 15, "late": 7, "none": 0, "submitted": -60, "excused": -60}

# ── Hard negative ─────────────────────────────────────────────────────────────
HARD_NEGATIVE_THRESHOLD = 5.0  # urgency pts apart → hard

# ── Canvas hook ───────────────────────────────────────────────────────────────
CANVAS_API = os.path.expanduser("~/.openclaw/hooks/canvas-api.sh")

# ── Current semester courses (Spring 2026) ────────────────────────────────────
SPRING_2026_COURSE_IDS = [
    224083,  # CS 2505 - Intro Computer Organization I
    224154,  # CS 3704 - Intermediate Software Design and Engineering
    224198,  # CS 3724 - Human-Computer Interaction
    225576,  # HD 3114 - Issues in Aging
    226986,  # NEUR 2464 - Neuroscience and Society
    223306,  # BMES 2004 - Concussion Perspectives
]

# ══════════════════════════════════════════════════════════════════════════════
# CANVAS DATA FETCHING
# ══════════════════════════════════════════════════════════════════════════════

def canvas_cmd(subcmd: str, *args, timeout: int = 30) -> list[dict] | None:
    cmd = [CANVAS_API, subcmd] + list(args)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def fetch_live_items() -> list[dict[str, Any]]:
    items = []
    seen = set()
    for cid in SPRING_2026_COURSE_IDS:
        raw_list = canvas_cmd("upcoming", str(cid))
        if not raw_list:
            continue
        for raw in raw_list:
            item_id = str(raw.get("id", ""))
            if item_id in seen:
                continue
            seen.add(item_id)
            assignment = raw.get("assignment", {})
            course_name = raw.get("context_name", "")
            items.append({
                "id": item_id,
                "key": item_id,
                "title": raw.get("title", "(untitled)"),
                "ptype": raw.get("type", "assignment"),
                "course_id": assignment.get("course_id", cid),
                "course_name": course_name,
                "course_code": _course_code(course_name),
                "due_iso": assignment.get("due_at", "") or "",
                "points": assignment.get("points_possible", 0) or 0,
                "submission_types": assignment.get("submission_types", []),
                "workflow_state": assignment.get("workflow_state", "published"),
                "status_flags": _derive_status_flags(assignment),
                "has_submitted": assignment.get("has_submitted_submissions", False),
                "weight": _estimate_weight(cid, assignment),
            })
    return items


def fetch_live_grades() -> dict[int, dict[str, float]]:
    grades = {}
    for cid in SPRING_2026_COURSE_IDS:
        data = canvas_cmd("grades", str(cid))
        if isinstance(data, dict):
            grades[cid] = {
                "current_score": data.get("current_score") or 0.0,
                "final_score": data.get("final_score") or 0.0,
            }
        else:
            grades[cid] = {"current_score": 0.0, "final_score": 0.0}
    return grades


def fetch_live_submissions() -> set[str]:
    submitted = set()
    for cid in SPRING_2026_COURSE_IDS:
        data = canvas_cmd("submissions", str(cid))
        if isinstance(data, list):
            for sub in data:
                if sub.get("workflow_state") == "submitted":
                    submitted.add(str(sub.get("assignment_id", "")))
    return submitted


def _course_code(course_name: str) -> str:
    words = course_name.split()
    return "".join(w[0] for w in words[:2]).upper() if len(words) >= 2 else course_name[:6].upper()


def _derive_status_flags(assignment: dict) -> list[str]:
    flags = []
    if assignment.get("has_submitted_submissions"):
        flags.append("submitted")
    elif assignment.get("graded_submissions_exist"):
        flags.append("missing")
    return flags


def _estimate_weight(course_id: int, assignment: dict) -> float:
    pts = float(assignment.get("points_possible", 0) or 0)
    if pts == 0:
        return 0.5
    if pts >= 100:
        return 10.0
    if pts >= 50:
        return 7.5
    if pts >= 20:
        return 5.0
    return 2.5


# ══════════════════════════════════════════════════════════════════════════════
# URGENCY SCORING
# ══════════════════════════════════════════════════════════════════════════════

def parse_due_iso(due_iso: str) -> dt.datetime | None:
    if not due_iso:
        return None
    try:
        iso = due_iso.replace("Z", "+00:00").replace(" ", "T")
        return dt.datetime.fromisoformat(iso)
    except Exception:
        return None


def compute_urgency(item: dict[str, Any], now: dt.datetime | None = None,
                    grades: dict[int, dict[str, float]] | None = None) -> float:
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    # Time factor
    time_factor = 0.0
    due_dt = parse_due_iso(item.get("due_iso", ""))
    if due_dt:
        delta_h = (due_dt.astimezone(dt.timezone.utc) - now).total_seconds() / 3600.0
        if delta_h < 0:
            time_factor = min(30.0, abs(delta_h) * 1.5 + 10.0)
        elif delta_h < 24:
            time_factor = 20.0 + (24 - delta_h) * 0.5
        elif delta_h < 48:
            time_factor = 15.0 + (48 - delta_h) * 0.25
        elif delta_h < 168:
            time_factor = max(0, (168 - delta_h) / 24) * 1.5

    # Type factor
    ptype = (item.get("ptype") or "").lower()
    type_factor = next((s for t, s in _TYPE_SCORES.items() if t in ptype), 0.0)

    # Points factor (max +8)
    points_factor = min(8.0, float(item.get("points") or 0) / 25.0)

    # Status factor
    status_factor = 0.0
    for flag in item.get("status_flags", []):
        fl = flag.lower()
        if fl in _STATUS_SCORES:
            status_factor += _STATUS_SCORES[fl]
        elif "late" in fl:
            status_factor += _STATUS_SCORES["late"]

    # Grade impact factor
    grade_factor = 0.0
    course_id = item.get("course_id")
    weight = float(item.get("weight") or 0.0)
    if course_id and grades and course_id in grades and weight > 0:
        cur = grades[course_id].get("current_score", 0.0)
        fin = grades[course_id].get("final_score", 100.0)
        if fin > 0:
            grade_factor = min(10.0, weight * (100.0 - cur) / 100.0)

    return max(0.0,
        W_TIME * time_factor
        + W_TYPE * type_factor
        + W_POINTS * points_factor
        + W_STATUS * status_factor
        + W_GRADE_IMPACT * grade_factor)


def compute_grade_impact(item: dict, grades: dict[int, dict[str, float]] | None) -> float:
    course_id = item.get("course_id")
    weight = float(item.get("weight") or 0.0)
    if not course_id or weight == 0 or not grades or course_id not in grades:
        return 0.0
    cur = grades[course_id].get("current_score", 0.0)
    fin = grades[course_id].get("final_score", 100.0)
    if fin <= 0:
        return 0.0
    return min(10.0, weight * (100.0 - cur) / 100.0)


# ══════════════════════════════════════════════════════════════════════════════
# SERIALIZATION
# ══════════════════════════════════════════════════════════════════════════════

def serialize_item(item: dict[str, Any]) -> str:
    parts = []
    ptype = (item.get("ptype") or "?").lower()
    badge_map = {"assignment": "ASGN", "quiz": "QUIZ", "exam": "EXAM",
                 "discussion": "DISC", "event": "EVNT", "announcement": "NOTE"}
    parts.append(f"[{badge_map.get(ptype, ptype[:4].upper())}]")
    parts.append((item.get("title") or "(untitled)")[:45])
    if item.get("course_code"):
        parts.append(f"@{item['course_code']}")
    due_dt = parse_due_iso(item.get("due_iso", ""))
    if due_dt:
        now = dt.datetime.now(dt.timezone.utc)
        delta_h = (due_dt.astimezone(dt.timezone.utc) - now).total_seconds() / 3600.0
        if delta_h < -1:
            parts.append("OVERDUE")
        elif delta_h < 24:
            parts.append("Today")
        elif delta_h < 48:
            parts.append("Tomorrow")
        else:
            parts.append(f"Due {due_dt.strftime('%m/%d %H:%M')}")
    pts = item.get("points", 0)
    if pts:
        parts.append(f"{float(pts):.0f}pts")
    flags = item.get("status_flags", [])
    flag_str = " ".join(f.lower() for f in flags)
    if "missing" in flag_str:
        parts.append("MISSING")
    elif "late" in flag_str:
        parts.append("LATE")
    elif "submitted" in flag_str:
        parts.append("DONE")
    return " ".join(parts)


def serialize_item_dict(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title", ""),
        "type": item.get("ptype", ""),
        "course": item.get("course_code", ""),
        "course_name": item.get("course_name", ""),
        "due_iso": item.get("due_iso", ""),
        "points": float(item.get("points") or 0),
        "status": _primary_status(item),
        "grade_impact": round(item.get("_grade_impact", 0.0), 2),
        "serialized": serialize_item(item),
    }


def _primary_status(item: dict) -> str:
    for f in item.get("status_flags", []):
        if f.lower() in ("missing", "late", "submitted", "excused"):
            return f.lower()
    return "none"


# ══════════════════════════════════════════════════════════════════════════════
# SELF-SUPERVISED SIGNALS
# ══════════════════════════════════════════════════════════════════════════════

def compute_signals(item_a: dict, item_b: dict, score_a: float, score_b: float) -> list[str]:
    signals = []
    now = dt.datetime.now(dt.timezone.utc)

    # Time ordering
    flags_a = item_a.get("status_flags", [])
    flags_b = item_b.get("status_flags", [])
    spec_a = any(f.lower() in ("missing", "late", "submitted") for f in flags_a)
    spec_b = any(f.lower() in ("missing", "late", "submitted") for f in flags_b)
    if not spec_a and not spec_b:
        da = parse_due_iso(item_a.get("due_iso", ""))
        db = parse_due_iso(item_b.get("due_iso", ""))
        if da and db:
            signals.append("time_ordering")
            if da == db:
                signals.append("time_tie")

    # Type hierarchy
    ta = (item_a.get("ptype") or "").lower()
    tb = (item_b.get("ptype") or "").lower()
    sa = next((v for t, v in _TYPE_SCORES.items() if t in ta), 0)
    sb = next((v for t, v in _TYPE_SCORES.items() if t in tb), 0)
    if sa != sb:
        signals.append("type_hierarchy")

    # Points ordering (same type)
    if ta == tb and ta not in ("event", "announcement"):
        if item_a.get("points", 0) != item_b.get("points", 0):
            signals.append("points_ordering")

    # Status ordering
    if spec_a or spec_b:
        ra = max((_STATUS_SCORES[f.lower()] for f in flags_a if f.lower() in _STATUS_SCORES), default=0)
        rb = max((_STATUS_SCORES[f.lower()] for f in flags_b if f.lower() in _STATUS_SCORES), default=0)
        if ra != rb:
            signals.append("status_ordering")

    # Grade impact
    gi_a = item_a.get("_grade_impact", 0.0)
    gi_b = item_b.get("_grade_impact", 0.0)
    if gi_a > 0 and gi_b > 0 and abs(gi_a - gi_b) > 0.5:
        signals.append("grade_impact")

    return signals


# ══════════════════════════════════════════════════════════════════════════════
# EXPLANATION GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_explanation(item_a: dict, item_b: dict, score_a: float, score_b: float) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    parts = []

    title_a = (item_a.get("title") or "?")[:40]
    title_b = (item_b.get("title") or "?")[:40]
    code_a = item_a.get("course_code", "?")
    code_b = item_b.get("course_code", "?")
    pts_a = float(item_a.get("points") or 0)
    pts_b = float(item_b.get("points") or 0)

    due_a = parse_due_iso(item_a.get("due_iso", ""))
    due_b = parse_due_iso(item_b.get("due_iso", ""))

    if due_a and due_b:
        da_h = (due_a.astimezone(dt.timezone.utc) - now).total_seconds() / 3600.0
        db_h = (due_b.astimezone(dt.timezone.utc) - now).total_seconds() / 3600.0
        if da_h < 0 or db_h < 0:
            overdue_item = title_a if da_h < db_h else title_b
            overdue_code = code_a if da_h < db_h else code_b
            h_overdue = abs(da_h if da_h < db_h else db_h)
            parts.append(
                f"{overdue_item} ({overdue_code}) is overdue by {h_overdue:.0f} hours — needs immediate attention"
            )
        elif abs(da_h - db_h) < 2:
            pass  # don't mention minor time diffs
        else:
            if da_h < db_h:
                parts.append(
                    f"{title_a} ({code_a}) is due in {da_h:.0f}h vs {code_b}'s {db_h:.0f}h — tighter deadline"
                )
            else:
                parts.append(
                    f"{title_b} ({code_b}) is due in {db_h:.0f}h vs {code_a}'s {da_h:.0f}h — tighter deadline"
                )
    elif due_a:
        parts.append(f"{title_a} ({code_a}) has a specific due date; {code_b} does not")
    elif due_b:
        parts.append(f"{title_b} ({code_b}) has a specific due date; {code_a} does not")

    if pts_a != pts_b:
        if pts_a > pts_b:
            parts.append(f"{title_a} ({code_a}) is worth {pts_a:.0f}pts — more than {code_b}'s {pts_b:.0f}pts")
        else:
            parts.append(f"{title_b} ({code_b}) is worth {pts_b:.0f}pts — more than {code_a}'s {pts_a:.0f}pts")

    ptype_a = (item_a.get("ptype") or "").lower()
    ptype_b = (item_b.get("ptype") or "").lower()
    if ptype_a != ptype_b:
        names = {"exam": "an exam", "quiz": "a quiz", "assignment": "an assignment",
                 "discussion": "a discussion", "event": "an event"}
        na = names.get(ptype_a, ptype_a)
        nb = names.get(ptype_b, ptype_b)
        sa = next((v for t, v in _TYPE_SCORES.items() if t in ptype_a), 0)
        sb = next((v for t, v in _TYPE_SCORES.items() if t in ptype_b), 0)
        if sa > sb:
            parts.append(f"{title_a} is {na}, a higher-priority item type than {nb}")
        else:
            parts.append(f"{title_b} is {nb}, a higher-priority item type than {na}")

    flags_a = item_a.get("status_flags", [])
    flags_b = item_b.get("status_flags", [])
    fstr_a = " ".join(f.lower() for f in flags_a)
    fstr_b = " ".join(f.lower() for f in flags_b)
    if "missing" in fstr_a:
        parts.append(f"{title_a} ({code_a}) is MISSING — needs immediate action")
    elif "missing" in fstr_b:
        parts.append(f"{title_b} ({code_b}) is MISSING — needs immediate action")
    if "late" in fstr_a:
        parts.append(f"{title_a} ({code_a}) is late")
    elif "late" in fstr_b:
        parts.append(f"{title_b} ({code_b}) is late")

    gi_a = item_a.get("_grade_impact", 0.0)
    gi_b = item_b.get("_grade_impact", 0.0)
    if gi_a > gi_b and gi_a > 0:
        parts.append(f"{title_a} ({code_a}) could significantly boost your grade (impact {gi_a:.1f})")
    elif gi_b > gi_a and gi_b > 0:
        parts.append(f"{title_b} ({code_b}) could significantly boost your grade (impact {gi_b:.1f})")

    if not parts:
        delta = abs(score_a - score_b)
        if delta < 5:
            return (f"{title_a} ({code_a}) and {title_b} ({code_b}) are nearly equivalent "
                    f"(urgency {score_a:.1f} vs {score_b:.1f}) — this is a hard negative for fine-grained ranking")
        else:
            winner = title_a if score_a > score_b else title_b
            return f"{winner} ranks higher (urgency {max(score_a, score_b):.1f} vs {min(score_a, score_b):.1f})"

    return " | ".join(parts[:3])


# ══════════════════════════════════════════════════════════════════════════════
# PAIR GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_pairs(items: list[dict[str, Any]], query: str, pair_type: str,
                   grades: dict[int, dict[str, float]] | None = None) -> list[dict[str, Any]]:
    pairs = []

    # Pre-compute
    for item in items:
        item["_urgency"] = compute_urgency(item, grades=grades)
        item["_grade_impact"] = compute_grade_impact(item, grades) if grades else 0.0

    scored = sorted(items, key=lambda x: -x["_urgency"])

    def make_pair(a: dict, b: dict, diff: float, ptype: str) -> dict:
        score_a, score_b = a["_urgency"], b["_urgency"]
        signals = compute_signals(a, b, score_a, score_b)
        # Difficulty
        if diff < 3.0:
            difficulty = "hard"
        elif diff < 10.0:
            difficulty = "medium"
        else:
            difficulty = "easy"
        # Preference (flip randomly for balance in standard/cross/same-course)
        if abs(score_a - score_b) < 1.5:
            preference = -1
        elif score_a >= score_b:
            preference = 1
        else:
            preference = 0
        return {
            "query": query,
            "item_a": serialize_item_dict(a),
            "item_b": serialize_item_dict(b),
            "preference": preference,
            "urgency_a": round(score_a, 2),
            "urgency_b": round(score_b, 2),
            "reason": generate_explanation(a, b, score_a, score_b),
            "pair_type": ptype,
            "difficulty": difficulty,
            "signals": signals,
        }

    if pair_type == "standard":
        for i, a in enumerate(scored):
            for b in scored[i + 1:]:
                diff = abs(a["_urgency"] - b["_urgency"])
                if diff < 1.0:
                    continue
                # Random flip for balanced preference labels
                if random.random() < 0.5:
                    a, b = b, a
                    diff = abs(a["_urgency"] - b["_urgency"])
                pairs.append(make_pair(a, b, diff, "standard"))

    elif pair_type == "equivalence":
        for i, a in enumerate(scored):
            for b in scored[i + 1:]:
                diff = abs(a["_urgency"] - b["_urgency"])
                if 0.5 <= diff <= HARD_NEGATIVE_THRESHOLD:
                    pairs.append(make_pair(a, b, diff, "equivalence"))

    elif pair_type == "contrast":
        n = len(scored)
        q = max(2, n // 4)
        top, bottom = scored[:q], scored[-q:]
        for a in top:
            for b in bottom:
                diff = abs(a["_urgency"] - b["_urgency"])
                if diff > 10.0:
                    pairs.append(make_pair(a, b, diff, "contrast"))

    elif pair_type == "same-course":
        by_course: dict[str, list] = {}
        for item in items:
            by_course.setdefault(str(item.get("course_id", "")), []).append(item)
        for cid, cis in by_course.items():
            if len(cis) < 2:
                continue
            cs = sorted(cis, key=lambda x: -x["_urgency"])
            for i, a in enumerate(cs):
                for b in cs[i + 1:]:
                    diff = abs(a["_urgency"] - b["_urgency"])
                    if diff >= 1.0:
                        if random.random() < 0.5:
                            a, b = b, a
                            diff = abs(a["_urgency"] - b["_urgency"])
                        pairs.append(make_pair(a, b, diff, "same-course"))

    elif pair_type == "cross-course":
        for i, a in enumerate(scored):
            for b in scored[i + 1:]:
                if str(a.get("course_id", "")) != str(b.get("course_id", "")):
                    diff = abs(a["_urgency"] - b["_urgency"])
                    if diff >= 1.0:
                        if random.random() < 0.5:
                            a, b = b, a
                            diff = abs(a["_urgency"] - b["_urgency"])
                        pairs.append(make_pair(a, b, diff, "cross-course"))

    return pairs


# ══════════════════════════════════════════════════════════════════════════════
# QUERY DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

QUERIES = [
    # (query_text, pair_type)
    ("what's due today",                    "standard"),
    ("what's due this week",               "standard"),
    ("what's overdue",                      "standard"),
    ("highest value assignments",           "standard"),
    ("assignments affecting my grade",      "standard"),
    ("upcoming exams and quizzes",          "standard"),
    ("all discussions",                     "standard"),
    ("sort by deadline",                    "standard"),
    ("sort by points",                      "standard"),
    ("sort by importance",                  "standard"),
    ("all items ranked by urgency",         "standard"),
    ("assignments nearly tied in urgency",   "equivalence"),
    ("compare top vs bottom priority items", "contrast"),
    ("rank assignments from the same course", "same-course"),
    ("prioritize across all my courses",     "cross-course"),
    ("highest impact assignments",           "contrast"),
    ("items ranked by grade importance",     "same-course"),
]


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE DATA
# ══════════════════════════════════════════════════════════════════════════════

def _make_sample_items() -> list[dict[str, Any]]:
    # Now = 2026-04-14 01:15 EDT = UTC
    BASE = dt.datetime(2026, 4, 14, 1, 15, tzinfo=dt.timezone.utc)

    def rh(h: int) -> str:
        return (BASE + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return [
        dict(key="s001", ptype="assignment",
             title="Homework 4 — Managing a Roster of Names in C",
             course_id=224083, course_code="CS2505", course_name="Intro Computer Organization I",
             due_iso=rh(-72), points=100.0, status_flags=["missing"], weight=10.0),

        dict(key="s002", ptype="quiz",
             title="NEUR 2464 Neuroimaging Quiz 2",
             course_id=226986, course_code="NEUR2464", course_name="Neuroscience and Society",
             due_iso=rh(-60), points=25.0, status_flags=["late"], weight=5.0),

        dict(key="s003", ptype="assignment",
             title="HD 3114 Reading Response Week 12",
             course_id=225576, course_code="HD3114", course_name="Issues in Aging",
             due_iso=rh(22), points=15.0, status_flags=[], weight=3.0),

        dict(key="s004", ptype="exam",
             title="CS 2505 Midterm 2 — C Programming",
             course_id=224083, course_code="CS2505", course_name="Intro Computer Organization I",
             due_iso=rh(46), points=200.0, status_flags=[], weight=20.0),

        dict(key="s005", ptype="discussion",
             title="NEUR 2464 Brain Connectivity Discussion",
             course_id=226986, course_code="NEUR2464", course_name="Neuroscience and Society",
             due_iso=rh(96), points=10.0, status_flags=[], weight=2.5),

        dict(key="s006", ptype="assignment",
             title="HD 3114 Research Summary Draft",
             course_id=225576, course_code="HD3114", course_name="Issues in Aging",
             due_iso=rh(120), points=200.0, status_flags=[], weight=15.0),

        dict(key="s007", ptype="quiz",
             title="NEUR 2464 fMRI Analysis Quiz",
             course_id=226986, course_code="NEUR2464", course_name="Neuroscience and Society",
             due_iso=rh(72), points=30.0, status_flags=[], weight=5.0),

        dict(key="s008", ptype="exam",
             title="CS 3724 HCI Final Exam — Prototyping and Evaluation",
             course_id=224198, course_code="CS3724", course_name="Human-Computer Interaction",
             due_iso=rh(168), points=150.0, status_flags=[], weight=18.0),

        dict(key="s009", ptype="assignment",
             title="Project phase 3 TME (Team Member Evaluation)",
             course_id=224198, course_code="CS3724", course_name="Human-Computer Interaction",
             due_iso=rh(50), points=1.0, status_flags=[], weight=0.5),

        dict(key="s010", ptype="discussion",
             title="CS 3704 Top Five Discussion Post (HW5)",
             course_id=224154, course_code="CS3704", course_name="Intermediate Software Design and Engineering",
             due_iso=rh(140), points=100.0, status_flags=[], weight=8.0),

        dict(key="s011", ptype="assignment",
             title="Activity 10: Empirical Evaluation",
             course_id=224198, course_code="CS3724", course_name="Human-Computer Interaction",
             due_iso=rh(200), points=2.0, status_flags=[], weight=0.5),

        dict(key="s012", ptype="assignment",
             title="NEUR 2464 Reading on addiction (group assignment)",
             course_id=226986, course_code="NEUR2464", course_name="Neuroscience and Society",
             due_iso=rh(240), points=10.0, status_flags=[], weight=2.0),

        dict(key="s013", ptype="assignment",
             title="CS 3704 Lab 4 — SQL Queries",
             course_id=224154, course_code="CS3704", course_name="Intermediate Software Design and Engineering",
             due_iso=rh(-120), points=50.0, status_flags=["submitted"], weight=5.0),

        dict(key="s014", ptype="announcement",
             title="CS 3704 Final Project Guidelines Posted",
             course_id=224154, course_code="CS3704", course_name="Intermediate Software Design and Engineering",
             due_iso=rh(48), points=0.0, status_flags=[], weight=0.0),

        dict(key="s015", ptype="assignment",
             title="Project phase 3: Prototyping",
             course_id=224198, course_code="CS3724", course_name="Human-Computer Interaction",
             due_iso=rh(180), points=5.0, status_flags=[], weight=12.0),
    ]


SAMPLE_GRADES: dict[int, dict[str, float]] = {
    224083: {"current_score": 90.69, "final_score": 90.0},
    224154: {"current_score": 96.64, "final_score": 62.24},
    224198: {"current_score": 90.97, "final_score": 30.95},
    225576: {"current_score": 93.83, "final_score": 88.0},
    226986: {"current_score": 97.83, "final_score": 89.38},
}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Canvas reranker training data")
    parser.add_argument("--output", "-o", default="data/rerank_train.jsonl")
    parser.add_argument("--limit", "-n", type=int, default=1500)
    parser.add_argument("--sample", action="store_true", help="Use hardcoded sample items")
    parser.add_argument("--live", action="store_true", help="Fetch live Canvas data")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    # Load items + grades
    if args.sample:
        print("[INFO] --sample mode: using hardcoded items")
        items = _make_sample_items()
        grades = SAMPLE_GRADES
    elif args.live:
        print("[INFO] --live mode: fetching Canvas data...")
        items = fetch_live_items()
        grades = fetch_live_grades()
        print(f"[INFO] Fetched {len(items)} items, {len(grades)} course grades")
        if not items:
            print("[WARN] No items fetched. Use --sample for offline testing.")
            sys.exit(1)
    else:
        print("[INFO] No --sample/--live specified. Using sample data.")
        items = _make_sample_items()
        grades = SAMPLE_GRADES

    # Generate pairs
    all_pairs = []
    for query, ptype in QUERIES:
        all_pairs.extend(generate_pairs(items, query, ptype, grades))

    # Deduplicate
    seen = set()
    unique = []
    for p in all_pairs:
        key = (p["item_a"]["title"][:40], p["item_b"]["title"][:40], p["query"])
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # Stats
    p1 = sum(1 for p in unique if p["preference"] == 1)
    p0 = sum(1 for p in unique if p["preference"] == 0)
    pm1 = sum(1 for p in unique if p["preference"] == -1)
    hard = sum(1 for p in unique if p["difficulty"] == "hard")
    by_type: dict[str, int] = {}
    for p in unique:
        by_type[p["pair_type"]] = by_type.get(p["pair_type"], 0) + 1

    print(f"[STATS] Total unique pairs: {len(unique)}")
    print(f"  Preference: A={p1}  B={p0}  tie={pm1}")
    print(f"  Difficulty: hard={hard}  medium={sum(1 for p in unique if p['difficulty']=='medium')}  easy={sum(1 for p in unique if p['difficulty']=='easy')}")
    print(f"  Pair types: {by_type}")

    # Limit
    if len(unique) > args.limit:
        random.shuffle(unique)
        unique = unique[:args.limit]

    # Write
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for p in unique:
            f.write(json.dumps(p) + "\n")
    print(f"\n[OK] Wrote {len(unique)} pairs → {out}")

    # Print 10 sample pairs
    print("\n" + "=" * 70)
    print("SAMPLE PAIRS (first 10)")
    print("=" * 70)
    pref_label = {1: "A", 0: "B", -1: "TIE"}
    for p in unique[:10]:
        print(f"\nQuery: {p['query']}")
        print(f"  Type={p['pair_type']} | Diff={p['difficulty']} | Pref={pref_label[p['preference']]} (u_a={p['urgency_a']}, u_b={p['urgency_b']})")
        print(f"  A: {p['item_a']['serialized']} [gi={p['item_a']['grade_impact']}]")
        print(f"  B: {p['item_b']['serialized']} [gi={p['item_b']['grade_impact']}]")
        print(f"  Reason: {p['reason'][:130]}")
        print(f"  Signals: {p['signals']}")


if __name__ == "__main__":
    main()