#!/usr/bin/env python3
"""
Canvas DPO Dataset Generator — v2
==================================
One file. Pure Python. No shell deps.

Features:
  - Fetches ALL courses across all years (not just current semester)
  - Pulls syllabus per course: extracts grade weights, exam dates, course type
  - Classifies every item by type: graded_assignment | participation | extra_credit |
    exam | ungraded_activity | ignore
  - Item-level anonymization: real titles replaced with structural descriptors
    (e.g. "100-point graded assignment, 3 days, unsubmitted")
  - Query: natural-language urgency question using the anonymized structure
  - Course-level anonymization: course IDs → COURSE001, etc.
  - Ignore signals: items labeled with WHY they're excluded or included

Teammates only need:
    pip install requests
    python3 generate_dataset.py --token vt_xxxx --handle alice --output data/collab/alice.jsonl
"""

import argparse
import json
import os
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests


# ── Config ─────────────────────────────────────────────────────────────────────

BASE_URL = "https://canvas.vt.edu/api/v1"


# ── Canvas Client ─────────────────────────────────────────────────────────────

class CanvasClient:
    def __init__(self, token: str, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/json"

    def get(self, path: str, params: Optional[dict] = None) -> list[dict]:
        url = f"{self.base_url}{path}"
        items: list[dict] = []
        while url:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data if isinstance(data, list) else [data])
            url = None
            link = resp.headers.get("Link", "")
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
            params = None
            total = int(resp.headers.get("X-Total", len(items) + 1))
            if len(items) >= total:
                break
        return items

    def get_quiet(self, path: str, params: Optional[dict] = None) -> list[dict]:
        try:
            return self.get(path, params)
        except requests.HTTPError as e:
            if e.response.status_code in (403, 404):
                return []
            raise


# ── Data Models ─────────────────────────────────────────────────────────────────

@dataclass
class CourseInfo:
    id: int
    code: str  # anonymized: COURSE001, etc.
    name: str  # full course name
    course_type: str  # cs_core | science_lab | humanities | elective | advising | test_site | other
    grade_weights: dict  # {"exams": 40, "assignments": 30, ...}
    exam_dates: list[str]
    credits: int
    syllabus_snippet: str  # first 500 chars
    term: str  # e.g. "Fall 2024", "Spring 2026"


@dataclass
class RankedItem:
    id: str
    course_id: int
    course_code: str  # anonymized: COURSE001
    # Anonymized structural title:
    #   "{points}-point {item_type}, {due_str}, {status}"
    #   e.g. "100-point graded assignment, due in 24h, unsubmitted"
    #   e.g. "0-point participation, no due date, unsubmitted"
    anon_title: str
    item_type: str  # graded_assignment | quiz | discussion | participation | exam | extra_credit | ungraded | ignore
    sub_type: str  # classroom_participation | graded_assessment | exam | extra_credit | ungraded_activity | ignore
    due_at: Optional[datetime]
    hours_until: Optional[float]  # always computed if due_at exists
    points: Optional[float]
    score: Optional[float]
    score_percent: Optional[float]
    submitted: bool
    missing: bool
    workflow_state: str
    group_weight: Optional[float]
    is_extra_credit: bool
    # Why this item is ranked / ignored — used as training signal
    ignore_reason: Optional[str]  # None = rankable; "no_due_date_participation" = skip urgency
    extra_credit: bool
    description: str  # kept for syllabus extraction, not in output


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Item Classification ─────────────────────────────────────────────────────────

def classify_item(a: dict, sub: dict, pts: Optional[float]) -> tuple[str, str, bool, Optional[str]]:
    """
    Classify an item. Returns (item_type, sub_type, is_extra_credit, ignore_reason).

    ignore_reason is set for items that are noise (no due date, ungraded participation
    with no urgency signal). Items with ignore_reason are still INCLUDED in output
    but with urgency_score=0 so the model can learn to handle them.

    sub_type categories:
      graded_assessment   — worth points, submitted for a grade
      classroom_participation — no points or 0pts, completion-based
      exam               — exam/quiz/test in the name
      extra_credit        — explicitly marked extra credit
      ungraded_activity  — no points, no grade, no due date
      ignore             — completely drop (not returned)
    """
    name = (a.get("name") or "").lower()
    ec = a.get("extra_credit", False) or sub.get("extra_credit", False)
    workflow = sub.get("workflow_state", a.get("workflow_state", ""))

    # Extra credit
    if ec:
        return "extra_credit", "extra_credit", True, None

    # Exams / tests — high urgency
    exam_keywords = ["exam", "midterm", "final", "test", "practical", "assessment"]
    if any(kw in name for kw in exam_keywords):
        return "exam", "exam", False, None

    # Graded quizzes / assignments / discussions — core rankable items
    if pts and pts > 0:
        return "graded_assignment", "graded_assessment", False, None

    # 0 points or None points — could be participation, ungraded, or syllabus noise
    if pts == 0 or pts is None:
        # Check if submission is tracked (points deducted for missing)
        if workflow in ("graded", "submitted", "needs_grading"):
            return "graded_assignment", "graded_assessment", False, None
        # Completion / participation items — low priority but included
        participation_kw = ["participation", "attendance", "discussion board", "forum",
                            "reflection", "journal", "check-in"]
        if any(kw in name for kw in participation_kw):
            return "participation", "classroom_participation", False, "no_due_date_participation"
        # Pop quizzes, in-class activities — included but low urgency
        if any(kw in name for kw in ["pop quiz", "in-class", "worksheet", "reading quiz"]):
            return "ungraded", "ungraded_activity", False, "no_due_date_participation"
        # Everything else with no points and no due date → ignore
        return "ignore", "ignore", False, "ungraded_no_points_no_due"

    return "graded_assignment", "graded_assessment", False, None


# ── Syllabus Extraction ─────────────────────────────────────────────────────────

def extract_grade_weights(syllabus_html: str) -> dict:
    """Parse grade weight breakdown from syllabus HTML."""
    weights: dict[str, float] = {}
    html_lower = syllabus_html.lower()

    # Common patterns: "Exams: 40%", "Exams (40% of grade)", "Grading: Exams 40%..."
    patterns = [
        r'(?:exams?|tests?|midterm|final)\s*:?\s*(\d+)\s*%',
        r'(\d+)\s*%\s*(?:exams?|tests?|midterm|final)',
        r'assignments?\s*:?\s*(\d+)\s*%',
        r'(\d+)\s*%\s*(?:assignments?|homework|problem sets?)',
        r'participation\s*:?\s*(\d+)\s*%',
        r'(\d+)\s*%\s*(?:participation|attendance|discussion)',
        r'projects?\s*:?\s*(\d+)\s*%',
        r'(\d+)\s*%\s*(?:project)',
        r'labs?\s*:?\s*(\d+)\s*%',
        r'(\d+)\s*%\s*(?:lab)',
    ]

    found = set()
    for p in patterns:
        for m in re.finditer(p, html_lower):
            val = float(m.group(1))
            if 5 <= val <= 70:  # reasonable weight range
                label = m.group(0).strip()
                # Normalize label
                for kw in ["exam", "test", "midterm", "final"]:
                    if kw in label:
                        found.add(("exams", val))
                for kw in ["assignment", "homework"]:
                    if kw in label:
                        found.add(("assignments", val))
                for kw in ["participation", "attendance", "discussion"]:
                    if kw in label:
                        found.add(("participation", val))
                for kw in ["project"]:
                    if kw in label:
                        found.add(("projects", val))

    return dict(found) if found else {}


def extract_exam_dates(syllabus_html: str) -> list[str]:
    """Extract exam dates from syllabus HTML text."""
    html_text = re.sub(r'<[^>]+>', ' ', syllabus_html)
    html_text = re.sub(r'\s+', ' ', html_text)

    # Look for month + day patterns
    dates = []
    month_names = "january|february|march|april|may|june|september|october|november|december"
    pattern = rf'\b({month_names})\s+\d{{1,2}}(?:,?\s+\d{{4}})?'
    for m in re.finditer(pattern, html_text, re.IGNORECASE):
        dates.append(m.group(0))

    # Also look for date strings like "3/15/2026"
    pattern2 = r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b'
    for m in re.finditer(pattern2, html_text):
        d = m.group(0)
        if d not in dates:
            dates.append(d)

    return list(set(dates))[:10]  # dedupe, max 10


def guess_course_type(code: str, name: str) -> str:
    """Guess course type from code + name for syllabus context."""
    combined = (code + " " + name).lower()

    cs_kw = ["cs_", "computer", "software", "data structures", "algorithms",
             "systems programming", "hci", "software design", "data science"]
    if any(kw in combined for kw in cs_kw):
        return "cs_core"

    sci_kw = ["bio", "chem", "phys", "neuro", "neurobio", "anatomy", "biochem",
              "neuroscience", "lab", "organic", "physics"]
    if any(kw in combined for kw in sci_kw):
        return "science_lab"

    hum_kw = ["phil", "history", "english", "writing", "literature", "sociology",
              "psych", "econ", "anthropology", "political", "religion"]
    if any(kw in combined for kw in hum_kw):
        return "humanities"

    # Test / advising / one-off sites
    if any(kw in combined for kw in ["respondus", "advising", "integrity", "virtual community"]):
        return "test_site"

    return "elective"


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_syllabus(client: CanvasClient, course_id: int) -> tuple[str, str]:
    """Fetch syllabus HTML and extract grade weights + exam dates."""
    try:
        resp = client.session.get(
            f"{client.base_url}/courses/{course_id}/assignments",
            timeout=20,
        )
        resp.raise_for_status()
        # Get syllabus from first assignment or course
        syllabus_url = f"{client.base_url}/courses/{course_id}"
    except Exception:
        pass

    # Try the syllabus endpoint
    try:
        resp = client.session.get(
            f"{client.base_url}/courses/{course_id}/extras",
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            html = data.get("syllabus", "") or data.get("syllabus_body", "") or ""
            return html, extract_grade_weights(html)
    except Exception:
        pass

    return "", {}


def fetch_all(client: CanvasClient) -> tuple[list[RankedItem], list[CourseInfo]]:
    """Fetch items and syllabus from all enrolled courses (all years)."""
    items: list[RankedItem] = []
    course_infos: list[CourseInfo] = []

    print("Fetching all courses (all years)...")
    courses = client.get(
        "/users/self/courses",
        {"enrollment_state": "all", "include": ["total_scores"]},
    )
    print(f"  {len(courses)} total enrollments\n")

    now = datetime.now(timezone.utc)
    course_counter = 0

    for course in courses:
        cid = course["id"]
        code_raw = course.get("course_code", f"COURSE{cid}")
        name_raw = course.get("name", "Unknown Course")
        course_counter += 1

        # Build anonymized course code
        course_code = f"COURSE{str(course_counter).zfill(3)}"

        # Extract syllabus
        syllabus_html = ""
        grade_weights: dict = {}
        exam_dates: list[str] = []

        # Try to get syllabus via assignments endpoint (Canvas gives syllabus via this)
        try:
            syllabus_html = course.get("syllabus", "") or ""
            if syllabus_html:
                grade_weights = extract_grade_weights(syllabus_html)
                exam_dates = extract_exam_dates(syllabus_html)
        except Exception:
            pass

        # If syllabus field is empty, try the content API
        if not syllabus_html:
            try:
                content_resp = client.session.get(
                    f"{client.base_url}/courses/{cid}/content",
                    timeout=15,
                )
                if content_resp.status_code == 200:
                    content_html = content_resp.json().get("body", "") or ""
                    grade_weights = extract_grade_weights(content_html)
                    exam_dates = extract_exam_dates(content_html)
            except Exception:
                pass

        course_type = guess_course_type(code_raw, name_raw)
        term = course.get("term", {}).get("name", "unknown")
        credits = course.get("credits", 3)

        course_infos.append(CourseInfo(
            id=cid,
            code=course_code,
            name=name_raw,
            course_type=course_type,
            grade_weights=grade_weights,
            exam_dates=exam_dates,
            credits=credits,
            syllabus_snippet=syllabus_html[:500] if syllabus_html else "",
            term=term,
        ))

        # Get assignment group weights
        group_weights: dict[int, float] = {}
        for grp in client.get_quiet(f"/courses/{cid}/assignment_groups"):
            w = grp.get("group_weight", 0.0)
            if w > 0:
                group_weights[grp["id"]] = w

        print(f"  [{course_code}] {code_raw} ({course_type})...", end="", flush=True)
        count = 0

        # ── Assignments ──────────────────────────────────────────────────────
        for a in client.get_quiet(f"/courses/{cid}/assignments", {"order_by": "due_at"}):
            sub = a.get("submission", {}) or {}
            pts = a.get("points_possible")
            due = _parse_dt(a.get("due_at"))
            gid = a.get("assignment_group_id", 0)

            item_type, sub_type, is_ec, ignore_reason = classify_item(a, sub, pts)

            if sub_type == "ignore":
                continue

            score_pct: Optional[float] = None
            if sub.get("score") is not None and pts and pts > 0:
                score_pct = sub.get("score") / pts * 100

            # Build anonymized title
            anon_title = _build_anon_title(item_type, pts, due, sub.get("submitted_at"), sub.get("score"), sub.get("missing"))

            items.append(RankedItem(
                id=f"{cid}_assignment_{a['id']}",
                course_id=cid,
                course_code=course_code,
                anon_title=anon_title,
                item_type=item_type,
                sub_type=sub_type,
                due_at=due,
                hours_until=_hours_until(due) if due else None,
                points=pts,
                score=sub.get("score"),
                score_percent=score_pct,
                submitted=sub.get("submitted_at") is not None,
                missing=bool(sub.get("missing")),
                workflow_state=sub.get("workflow_state", a.get("workflow_state", "published")),
                group_weight=group_weights.get(gid),
                is_extra_credit=is_ec,
                ignore_reason=ignore_reason,
                extra_credit=is_ec,
                description=a.get("description", "") or "",
            ))
            count += 1

        # ── Quizzes ─────────────────────────────────────────────────────────
        for q in client.get_quiet(f"/courses/{cid}/quizzes"):
            sub = q.get("submission", {}) or {}
            pts = q.get("points_possible")
            due = _parse_dt(q.get("due_at"))

            item_type, sub_type, is_ec, ignore_reason = classify_item(q, sub, pts)

            if sub_type == "ignore":
                continue

            score_pct: Optional[float] = None
            if sub.get("score") is not None and pts and pts > 0:
                score_pct = sub.get("score") / pts * 100

            anon_title = _build_anon_title(item_type, pts, due, sub.get("submitted_at"), sub.get("score"), sub.get("missing"))

            items.append(RankedItem(
                id=f"{cid}_quiz_{q['id']}",
                course_id=cid,
                course_code=course_code,
                anon_title=anon_title,
                item_type="quiz",
                sub_type=sub_type,
                due_at=due,
                hours_until=_hours_until(due) if due else None,
                points=pts,
                score=sub.get("score"),
                score_percent=score_pct,
                submitted=sub.get("submitted_at") is not None,
                missing=bool(sub.get("missing")),
                workflow_state=sub.get("workflow_state", q.get("workflow_state", "published")),
                group_weight=None,
                is_extra_credit=is_ec,
                ignore_reason=ignore_reason,
                extra_credit=is_ec,
                description=q.get("description", "") or "",
            ))
            count += 1

        # ── Discussions ─────────────────────────────────────────────────────
        for d in client.get_quiet(f"/courses/{cid}/discussion_topics"):
            sub = d.get("submission", {}) or {}
            pts = d.get("points_possible")
            due = _parse_dt(d.get("due_at"))

            item_type, sub_type, is_ec, ignore_reason = classify_item(d, sub, pts)

            if sub_type == "ignore":
                continue

            score_pct: Optional[float] = None
            if sub.get("score") is not None and pts and pts > 0:
                score_pct = sub.get("score") / pts * 100

            anon_title = _build_anon_title(item_type, pts, due, sub.get("submitted_at"), sub.get("score"), sub.get("missing"))

            items.append(RankedItem(
                id=f"{cid}_discussion_{d['id']}",
                course_id=cid,
                course_code=course_code,
                anon_title=anon_title,
                item_type="discussion",
                sub_type=sub_type,
                due_at=due,
                hours_until=_hours_until(due) if due else None,
                points=pts,
                score=sub.get("score"),
                score_percent=score_pct,
                submitted=sub.get("submitted_at") is not None,
                missing=bool(sub.get("missing")),
                workflow_state=sub.get("workflow_state", d.get("workflow_state", "published")),
                group_weight=None,
                is_extra_credit=is_ec,
                ignore_reason=ignore_reason,
                extra_credit=is_ec,
                description=d.get("message", "") or "",
            ))
            count += 1

        print(f" {count} items")

    print(f"\nTotal items: {len(items)}")
    return items, course_infos


def _hours_until(due: Optional[datetime]) -> Optional[float]:
    if due is None:
        return None
    now = datetime.now(timezone.utc)
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return max(0.0, (due - now).total_seconds() / 3600)


def _due_str(hours: Optional[float]) -> str:
    if hours is None:
        return "no due date"
    if hours <= 0:
        return "overdue"
    if hours < 1:
        return f"due in {int(hours * 60)}min"
    if hours < 24:
        return f"due in {hours:.0f}h"
    if hours < 168:
        return f"due in {(hours / 24):.0f} days"
    return f"due in {(hours / 168):.0f} weeks"


def _build_anon_title(item_type: str, pts: Optional[float], due: Optional[datetime],
                       submitted_at: Optional[str], score: Optional[float],
                       missing: bool) -> str:
    """Build anonymized structural title from item attributes."""
    hours = _hours_until(due)
    due_desc = _due_str(hours)

    pts_desc = f"{int(pts)}-point" if pts and pts > 0 else "0-point"
    status_parts = []

    if missing:
        status_parts.append("MISSING")
    elif submitted_at:
        status_parts.append("submitted")
        if score is not None and pts and pts > 0:
            pct = score / pts * 100
            status_parts.append(f"scored {pct:.0f}%")
    else:
        status_parts.append("unsubmitted")

    status_str = ", ".join(status_parts)

    type_labels = {
        "graded_assignment": "graded assignment",
        "quiz": "graded quiz",
        "discussion": "graded discussion",
        "participation": "participation",
        "exam": "exam",
        "extra_credit": "extra credit",
        "ungraded": "ungraded activity",
    }
    type_label = type_labels.get(item_type, item_type)

    return f"{pts_desc} {type_label}, {due_desc}, {status_str}"


# ── Urgency Scoring ────────────────────────────────────────────────────────────

def urgency(item: RankedItem) -> float:
    """
    Urgency score 0–200. Higher = more urgent to work on.

    Items with ignore_reason still get a score so they're included in pairs
    (with urgency=0, so the model can learn to handle them as noise).
    """
    if item.ignore_reason is not None:
        return 0.0

    score = 0.0
    h = item.hours_until

    if h is not None:
        if h <= 0:
            score += 100  # overdue
        elif h <= 6:
            score += 80
        elif h <= 24:
            score += 60
        elif h <= 48:
            score += 40
        elif h <= 168:
            score += 20
        elif h <= 336:
            score += 10
        else:
            score += max(0.0, 5.0 - (h - 336) / 168 * 5.0)
    else:
        score += 2  # no due date = very low priority

    if item.points and item.points > 0:
        score += min(item.points / 10.0, 20.0)

    if item.missing:
        score += 30

    if not item.submitted and item.item_type != "participation":
        score += 10

    gw = item.group_weight
    pp = item.points
    if gw is not None and pp and pp > 0:
        score += gw * pp / 100.0

    sp = item.score_percent
    if sp is not None and sp < 70:
        score += (70 - sp) / 10.0

    return score


# ── Pair Generation ────────────────────────────────────────────────────────────

PAIR_TYPES = ["same_course_type", "same_course", "same_type", "cross_course"]


def classify_pair(a: RankedItem, b: RankedItem) -> str:
    if a.course_id == b.course_id and a.item_type == b.item_type:
        return "same_course_type"
    if a.course_id == b.course_id:
        return "same_course"
    if a.item_type == b.item_type:
        return "same_type"
    return "cross_course"


def diff_label(diff: float) -> str:
    if diff < 5:
        return "very_easy"
    if diff < 15:
        return "easy"
    if diff < 30:
        return "medium"
    return "hard"


def build_query(a: RankedItem, b: RankedItem, sa: float, sb: float) -> str:
    """Build natural-language query from anonymized item descriptors."""
    winner = a if sa > sb else b
    loser = b if sa > sb else a

    h_w = winner.hours_until
    h_l = loser.hours_until

    hw_str = _due_str(h_w)
    hl_str = _due_str(h_l)

    return (
        f"Which should I work on first: "
        f'"{winner.anon_title}" '
        f'or "{loser.anon_title}"?'
    )


def generate_pairs(items: list[RankedItem], n_pairs: int,
                   seed: int, min_diff: float) -> tuple[list[dict], int]:
    random.seed(seed)
    scored = [(item, urgency(item)) for item in items]
    scored.sort(key=lambda x: x[1], reverse=True)

    pairs: list[dict] = []
    attempts = 0
    max_attempts = n_pairs * 10

    while len(pairs) < n_pairs and attempts < max_attempts:
        attempts += 1
        a_item, sa = random.choice(scored)
        b_item, sb = random.choice(scored)
        if a_item.id == b_item.id:
            continue

        diff = abs(sa - sb)
        if diff < min_diff:
            continue

        item_a_preferred = 1 if sa > sb else 0
        pair_type = classify_pair(a_item, b_item)
        difficulty = diff_label(diff)

        pa = a_item.points or 0
        pb = b_item.points or 0
        pts_ratio = max(pa / pb, pb / pa) if pa > 0 and pb > 0 else 1.0

        pair = {
            "query": build_query(a_item, b_item, sa, sb),
            "item_a": {
                "anon_title": a_item.anon_title,
                "course": a_item.course_code,
                "type": a_item.item_type,
                "sub_type": a_item.sub_type,
                "points": a_item.points,
                "hours_until": a_item.hours_until,
                "submitted": a_item.submitted,
                "missing": a_item.missing,
                "score_percent": a_item.score_percent,
                "urgency_score": round(sa, 2),
                "is_extra_credit": a_item.extra_credit,
                "ignore_reason": a_item.ignore_reason,
            },
            "item_b": {
                "anon_title": b_item.anon_title,
                "course": b_item.course_code,
                "type": b_item.item_type,
                "sub_type": b_item.sub_type,
                "points": b_item.points,
                "hours_until": b_item.hours_until,
                "submitted": b_item.submitted,
                "missing": b_item.missing,
                "score_percent": b_item.score_percent,
                "urgency_score": round(sb, 2),
                "is_extra_credit": b_item.extra_credit,
                "ignore_reason": b_item.ignore_reason,
            },
            "preference": item_a_preferred,
            "urgency_diff": round(diff, 2),
            "winner_urgency": round(max(sa, sb), 2),
            "loser_urgency": round(min(sa, sb), 2),
            "pair_type": pair_type,
            "difficulty": difficulty,
            "signals": {
                "time_pressure_winner": round(max(sa, sb) / 100.0, 3),
                "points_ratio": round(pts_ratio, 3),
                "same_course": a_item.course_id == b_item.course_id,
                "same_type": a_item.item_type == b_item.item_type,
                "has_ignore_signal": (a_item.ignore_reason is not None or b_item.ignore_reason is not None),
            },
        }
        pairs.append(pair)

    return pairs, attempts


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Canvas DPO Dataset Generator v2 — syllabus-aware, anonymized.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 generate_dataset.py --token vt_xxxx --handle alice --output data/collab/alice.jsonl
  python3 generate_dataset.py --token vt_xxxx --handle bob --output data/collab/bob.jsonl --n-pairs 2000
  python3 generate_dataset.py --token vt_xxxx --handle alice --output data/collab/alice.jsonl --min-diff 10

Output format: JSONL with two record types per file:
  1. metadata record: {"type": "metadata", "courses": [...], "generated_at": "..."}
  2. pair records: {"type": "pair", ...}

All item titles are anonymized to structural descriptors.
Course IDs are mapped to COURSE001, COURSE002, etc.
""",
    )
    parser.add_argument("--token", help="Canvas API token (or set CANVAS_TOKEN env var)")
    parser.add_argument("--handle", required=True, help="Your handle (for output logging)")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--n-pairs", type=int, default=None, help="Target pair count (default: auto)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--min-diff", type=float, default=3.0, help="Min urgency diff to keep pair (default: 3.0)")
    parser.add_argument("--base-url", default=BASE_URL, help="Canvas base URL")
    args = parser.parse_args()

    token = args.token or os.environ.get("CANVAS_TOKEN", "")
    if not token:
        print("ERROR: No token. Pass --token or set CANVAS_TOKEN env var.")
        print("Get token at: https://canvas.vt.edu/profile")
        sys.exit(1)

    print("=== Canvas DPO Dataset Generator v2 ===")
    print(f"Handle: {args.handle}")
    print(f"Output: {args.output}\n")

    client = CanvasClient(token=token, base_url=args.base_url)

    # Step 1: Fetch all
    print("Step 1: Fetching all courses and items...")
    try:
        raw_items, course_infos = fetch_all(client)
    except Exception as e:
        print(f"Fetch error: {e}")
        sys.exit(1)

    if not raw_items:
        print("ERROR: No items collected. Check your token and Canvas URL.")
        sys.exit(1)

    # Step 2: Count classification
    type_counts: dict = {}
    ignore_counts: dict = {}
    for item in raw_items:
        t = item.item_type
        type_counts[t] = type_counts.get(t, 0) + 1
        if item.ignore_reason:
            ir = item.ignore_reason
            ignore_counts[ir] = ignore_counts.get(ir, 0) + 1

    print(f"\nItem classification:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")
    if ignore_counts:
        print("  (ignore reasons:")
        for ir, c in sorted(ignore_counts.items(), key=lambda x: -x[1]):
            print(f"    {ir}: {c}")

    # Step 3: Generate pairs
    n = args.n_pairs
    if n is None:
        n = max(200, len(raw_items) * 5)
    print(f"\nStep 2: Generating {n} pairs (seed={args.seed}, min_diff={args.min_diff})...")
    pairs, attempts = generate_pairs(raw_items, n, args.seed, args.min_diff)
    print(f"  {len(pairs)} pairs from {attempts} attempts")

    # Step 4: Write output
    print(f"\nStep 3: Writing to {args.output}...")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)

    with open(args.output, "w") as f:
        # Write metadata header
        metadata = {
            "type": "metadata",
            "handle": args.handle,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_items": len(raw_items),
            "n_pairs": len(pairs),
            "seed": args.seed,
            "min_diff": args.min_diff,
            "course_map": {ci.id: ci.code for ci in course_infos},
            "courses": [
                {
                    "code": ci.code,
                    "name": ci.name,
                    "course_type": ci.course_type,
                    "grade_weights": ci.grade_weights,
                    "exam_dates": ci.exam_dates,
                    "credits": ci.credits,
                    "term": ci.term,
                }
                for ci in course_infos
            ],
        }
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")

        # Write pairs
        for p in pairs:
            p_out = dict(p)
            p_out["type"] = "pair"
            f.write(json.dumps(p_out, ensure_ascii=False) + "\n")

    print(f"Done. {len(pairs)} pairs written.")
    print(f"  Items: {len(raw_items)}, Courses: {len(course_infos)}")

    # Stats
    d_counts = {"very_easy": 0, "easy": 0, "medium": 0, "hard": 0}
    t_counts = {t: 0 for t in PAIR_TYPES}
    has_signal = 0
    diffs = []
    for p in pairs:
        d_counts[p["difficulty"]] = d_counts.get(p["difficulty"], 0) + 1
        t_counts[p["pair_type"]] = t_counts.get(p["pair_type"], 0) + 1
        if p["signals"]["has_ignore_signal"]:
            has_signal += 1
        diffs.append(p["urgency_diff"])

    import statistics
    print(f"\nStats:")
    print(f"  Urgency diff — mean: {statistics.mean(diffs):.1f}, min: {min(diffs):.1f}, max: {max(diffs):.1f}")
    print(f"  Difficulty: {d_counts}")
    print(f"  Pair types: {t_counts}")
    print(f"  Pairs with ignore signal (noise items): {has_signal}")

    # Sample
    with open(args.output) as f:
        meta = json.loads(f.readline())
        first_pair = json.loads(f.readline())

    print(f"\nMetadata: {len(meta['courses'])} courses anonymized")
    print(f"Sample pair:")
    print(f"  Query: {first_pair['query']}")
    print(f"  item_a: {first_pair['item_a']['anon_title']} | {first_pair['item_a']['course']} | urgency={first_pair['item_a']['urgency_score']}")
    print(f"  item_b: {first_pair['item_b']['anon_title']} | {first_pair['item_b']['course']} | urgency={first_pair['item_b']['urgency_score']}")
    print(f"  Winner: {'item_a' if first_pair['preference'] == 1 else 'item_b'} | diff={first_pair['urgency_diff']}")


if __name__ == "__main__":
    main()