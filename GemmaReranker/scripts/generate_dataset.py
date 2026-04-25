#!/usr/bin/env python3
"""
Canvas DPO Dataset Generator
============================
One file. No shell scripts. No hardcoded course IDs.

Teammates only need:
    pip install requests
    python3 generate_dataset.py --token vt_xxxx --handle yourname --output data/collab/yourname.jsonl

What it does:
  1. Fetches every active course via /users/self/courses
  2. Pulls assignments, quizzes, and discussion topics from each course
  3. Gets real grade signals: points_possible, current_score, missing, submission state
  4. Cleans out submitted/graded/past items — keeps only rankable upcoming work
  5. Generates urgency-scored DPO pairs (preference = higher urgency wins)
  6. Anonymizes course codes → COURSE001, COURSE002, etc.
  7. Writes JSONL ready for Path B training

The urgency score is based on:
  - Hours until due (exponential: overdue=100, <6h=80, <24h=60...)
  - Points possible (grade impact)
  - Missing flag (+30)
  - Unsubmitted (+10)
  - Assignment group weight × points
  - Underperformance on item (score < 70%)
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from typing import Optional

import requests


# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "https://canvas.vt.edu/api/v1"


# ── Canvas Client ───────────────────────────────────────────────────────────────

class CanvasClient:
    def __init__(self, token: str, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/json"

    def get(self, path: str, params: Optional[dict] = None) -> list[dict]:
        """Paginated GET. Fetches all pages automatically."""
        url = f"{self.base_url}{path}"
        items: list[dict] = []

        while url:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data if isinstance(data, list) else [data])

            # Pagination
            url = None
            link = resp.headers.get("Link", "")
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
            params = None  # don't re-send on cursor pages

            total = int(resp.headers.get("X-Total", len(items) + 1))
            if len(items) >= total:
                break

        return items

    def get_quiet(self, path: str, params: Optional[dict] = None) -> list[dict]:
        """GET that swallows 403s/404s (e.g. test sites, disabled tools)."""
        try:
            return self.get(path, params)
        except requests.HTTPError as e:
            if e.response.status_code in (403, 404):
                return []
            raise


# ── Data model ─────────────────────────────────────────────────────────────────

class Item:
    def __init__(
        self,
        item_id: str,
        course_id: int,
        course_code: str,
        title: str,
        item_type: str,
        due_at: Optional[datetime],
        points: Optional[float],
        score: Optional[float],
        submitted: bool,
        missing: bool,
        workflow_state: str,
        group_weight: Optional[float],
        description: str,
    ):
        self.id = item_id
        self.course_id = course_id
        self.course_code = course_code
        self.title = title
        self.type = item_type
        self.due_at = due_at
        self.points = points
        self.score = score
        self.submitted = submitted
        self.missing = missing
        self.workflow_state = workflow_state
        self.group_weight = group_weight
        self.description = description

    def score_pct(self) -> Optional[float]:
        if self.score is not None and self.points and self.points > 0:
            return self.score / self.points * 100
        return None

    def hours_until_due(self) -> Optional[float]:
        if self.due_at is None:
            return None
        now = datetime.now(timezone.utc)
        due = self.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return max(0.0, (due - now).total_seconds() / 3600)


# ── Fetch all items from Canvas ─────────────────────────────────────────────────

def fetch_items(client: CanvasClient) -> list[Item]:
    """Fetch assignments, quizzes, and discussions from every active course."""
    items: list[Item] = []

    print("Fetching enrolled courses...")
    # Use 'all' to get the full 4-year history (not just active semester).
    # 'active' returns only ~16 courses (current-semester noise). 'all' returns 59.
    courses = client.get(
        "/users/self/courses",
        {"enrollment_state": "all", "include": ["total_scores"]},
    )
    print(f"  {len(courses)} total enrollments across all years")

    for course in courses:
        cid = course["id"]
        code = course.get("course_code", f"COURSE{cid}")

        # Assignment group weights — may 403 on test/advising sites
        group_weights: dict[int, float] = {}
        for grp in client.get_quiet(f"/courses/{cid}/assignment_groups"):
            w = grp.get("group_weight", 0.0)
            if w > 0:
                group_weights[grp["id"]] = w

        print(f"  [{code}] fetching...", end="", flush=True)

        # Assignments
        count = 0
        # Assignments — 403 possible on test/advising sites
        for a in client.get_quiet(f"/courses/{cid}/assignments", {"order_by": "due_at"}):
            sub = a.get("submission", {}) or {}
            pts = a.get("points_possible")
            score = sub.get("score")
            gid = a.get("assignment_group_id", 0)

            due = _parse_dt(a.get("due_at"))

            items.append(Item(
                item_id=f"{cid}_assignment_{a['id']}",
                course_id=cid,
                course_code=code,
                title=a.get("name", "Untitled"),
                item_type="assignment",
                due_at=due,
                points=pts,
                score=score,
                submitted=sub.get("submitted_at") is not None,
                missing=bool(sub.get("missing")),
                workflow_state=sub.get("workflow_state", a.get("workflow_state", "published")),
                group_weight=group_weights.get(gid),
                description=_strip_html(a.get("description", "") or "")[:200],
            ))
            count += 1

        # Quizzes (may 404 if course doesn't have quiz tool)
        for q in client.get_quiet(f"/courses/{cid}/quizzes"):
            sub = q.get("submission", {}) or {}
            due = _parse_dt(q.get("due_at"))

            items.append(Item(
                item_id=f"{cid}_quiz_{q['id']}",
                course_id=cid,
                course_code=code,
                title=q.get("title", "Untitled Quiz"),
                item_type="quiz",
                due_at=due,
                points=q.get("points_possible"),
                score=sub.get("score"),
                submitted=sub.get("submitted_at") is not None,
                missing=bool(sub.get("missing")),
                workflow_state=sub.get("workflow_state", q.get("workflow_state", "published")),
                group_weight=None,
                description=_strip_html(q.get("description", "") or "")[:200],
            ))
            count += 1

        # Discussions (may 404 if course doesn't have discussions)
        for d in client.get_quiet(f"/courses/{cid}/discussion_topics"):
            sub = d.get("submission", {}) or {}
            due = _parse_dt(d.get("due_at"))

            items.append(Item(
                item_id=f"{cid}_discussion_{d['id']}",
                course_id=cid,
                course_code=code,
                title=d.get("title", "Untitled Discussion"),
                item_type="discussion",
                due_at=due,
                points=d.get("points_possible"),
                score=sub.get("score"),
                submitted=sub.get("submitted_at") is not None,
                missing=bool(sub.get("missing")),
                workflow_state=sub.get("workflow_state", d.get("workflow_state", "published")),
                group_weight=None,
                description=_strip_html(d.get("message", "") or "")[:200],
            ))
            count += 1

        print(f" {count} items")

    print(f"\nTotal raw items: {len(items)}")
    return items


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _strip_html(text: str) -> str:
    """Remove HTML tags from description."""
    import re
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ── Clean items ─────────────────────────────────────────────────────────────────

def clean(items: list[Item]) -> list[Item]:
    """
    Keep only items meaningful for ranking.

    Drop:
      - Items with no due date (unrankable noise)
      - Items far in the past (>6 months) AND already submitted AND no grade signal
        (e.g. a 2022 assignment fully submitted with no score — nothing to learn from)

    Keep:
      - ALL upcoming items (any semester)
      - ALL overdue items
      - ALL unsubmitted items (any time)
      - ALL submitted-but-still-being-graded items
      - Past items where the student performed poorly (grade_signal = urgency)
    """
    now = datetime.now(timezone.utc)
    valid_states = {"published", "graded", "submitted", "unsubmitted",
                   "pending_review", "needs_grading"}
    cleaned = []

    for item in items:
        if item.due_at is None:
            continue  # no due date = can't compute urgency
        if item.workflow_state not in valid_states:
            continue

        due = item.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)


        # Deep past AND submitted AND no score = fully done, don't rank
        age_months = (now - due).total_seconds() / (3600 * 24 * 30)
        if age_months > 6 and item.submitted and item.score is None:
            continue

        cleaned.append(item)

    dropped = len(items) - len(cleaned)
    print(f"Cleaned: {len(items)} → {len(cleaned)} (dropped {dropped})  "
          f"# items without due date or 6+ months old+submitted")
    return cleaned


# ── Urgency scoring ─────────────────────────────────────────────────────────────

def urgency(item: Item) -> float:
    """
    Weighted urgency. Higher = more urgent.

    Scale (roughly): 0–200
      100+ : overdue
      60-80: due within 24h
      20-40: due within 1 week
      <10  : due far out or no pressure
    """
    score = 0.0
    now = datetime.now(timezone.utc)

    h = item.hours_until_due()

    if h is not None:
        if h <= 0:
            score += 100          # overdue
        elif h <= 6:
            score += 80
        elif h <= 24:
            score += 60
        elif h <= 48:
            score += 40
        elif h <= 168:            # 1 week
            score += 20
        elif h <= 336:            # 2 weeks
            score += 10
        else:
            score += max(0.0, 5.0 - (h - 336) / 168 * 5.0)
    else:
        score += 2                # no due date = low priority

    # Points
    if item.points and item.points > 0:
        score += min(item.points / 10.0, 20.0)

    # Missing
    if item.missing:
        score += 30

    # Unsubmitted (still actionable)
    if not item.submitted:
        score += 10

    # Grade impact: group weight × points
    gw = item.group_weight
    pp = item.points
    if gw is not None and pp and pp > 0:
        score += gw * pp / 100.0

    # Underperformance on this item
    sp = item.score_pct()
    if sp is not None and sp < 70:
        score += (70 - sp) / 10.0

    return score


# ── Generate pairs ──────────────────────────────────────────────────────────────

PAIR_TYPES = ["same_course_type", "same_course", "same_type", "cross_course"]


def pair_type(a: Item, b: Item) -> str:
    if a.course_id == b.course_id and a.type == b.type:
        return "same_course_type"
    if a.course_id == b.course_id:
        return "same_course"
    if a.type == b.type:
        return "same_type"
    return "cross_course"


def difficulty(diff: float) -> str:
    if diff < 10:
        return "hard"
    if diff < 25:
        return "medium"
    return "easy"


def generate_pairs(items: list[Item], n_pairs: int, seed: int, min_diff: float,
                   course_map: dict[int, str]) -> list[dict]:
    """
    Sample random item pairs. Only keep when urgency diff is meaningful.
    Anonymize course codes using course_map.
    """
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

        winner_item, loser_item = (a_item, b_item) if sa > sb else (b_item, a_item)
        win_score = max(sa, sb)
        lose_score = min(sa, sb)

        # Natural-language query
        h_w = winner_item.hours_until_due()
        h_l = loser_item.hours_until_due()
        dw = f"due in {h_w:.0f}h" if h_w is not None else "no due date"
        dl = f"due in {h_l:.0f}h" if h_l is not None else "no due date"

        c_w = course_map.get(winner_item.course_id, winner_item.course_code)
        c_l = course_map.get(loser_item.course_id, loser_item.course_code)

        query = (
            "Which assignment should I work on first: "
            + f'"{winner_item.title}" ({c_w}, {dw}) '
            + f'or "{loser_item.title}" ({c_l}, {dl})?'
        )

        item_a_preferred = 1 if sa > sb else 0

        # Symmetric points ratio
        pa = a_item.points or 0
        pb = b_item.points or 0
        if pa > 0 and pb > 0:
            pts_ratio = max(pa / pb, pb / pa)
        else:
            pts_ratio = 1.0

        pair = {
            "query": query,
            "item_a": {
                "title": a_item.title,
                "course": course_map.get(a_item.course_id, a_item.course_code),
                "type": a_item.type,
                "points": a_item.points,
                "due_in_hours": a_item.hours_until_due(),
                "missing": a_item.missing,
                "submitted": a_item.submitted,
                "score_percent": a_item.score_pct(),
                "urgency_score": round(sa, 2),
            },
            "item_b": {
                "title": b_item.title,
                "course": course_map.get(b_item.course_id, b_item.course_code),
                "type": b_item.type,
                "points": b_item.points,
                "due_in_hours": b_item.hours_until_due(),
                "missing": b_item.missing,
                "submitted": b_item.submitted,
                "score_percent": b_item.score_pct(),
                "urgency_score": round(sb, 2),
            },
            "preference": item_a_preferred,
            "urgency_diff": round(diff, 2),
            "winner_urgency": round(win_score, 2),
            "loser_urgency": round(lose_score, 2),
            "pair_type": pair_type(a_item, b_item),
            "difficulty": difficulty(diff),
            "signals": {
                "time_pressure_winner": round(win_score / 100.0, 3),
                "points_ratio": round(pts_ratio, 3),
                "same_course": a_item.course_id == b_item.course_id,
                "same_type": a_item.type == b_item.type,
            },
        }
        pairs.append(pair)

    return pairs, attempts


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Canvas DPO Dataset Generator — one file, no shell deps.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First time (you):
  python3 generate_dataset.py --token vt_xxxx --handle alice --output data/collab/alice.jsonl

  # Teammates just need their token:
  python3 generate_dataset.py --token vt_yyyy --handle bob --output data/collab/bob.jsonl

  # Adjust pair count:
  python3 generate_dataset.py --token vt_xxxx --handle alice --output data/collab/alice.jsonl --n-pairs 1000

  # Strict quality filter (keep only high-difficulty pairs):
  python3 generate_dataset.py --token vt_xxxx --handle alice --output data/collab/alice.jsonl --min-diff 20

Required env vars (alternative to --token):
  CANVAS_TOKEN   Your Canvas API token from canvas.vt.edu/profile
        """,
    )
    parser.add_argument("--token", help="Canvas API token (or set CANVAS_TOKEN env var)")
    parser.add_argument("--handle", required=True,
                        help="Your name/handle (used in output logging)")
    parser.add_argument("--output", required=True,
                        help="Output JSONL path, e.g. data/collab/alice.jsonl")
    parser.add_argument("--n-pairs", type=int, default=None,
                        help="Target pair count (default: auto = items × 5)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--min-diff", type=float, default=3.0,
                        help="Min urgency diff to keep pair (default: 3.0)")
    parser.add_argument("--base-url", default=BASE_URL,
                        help="Canvas base URL (default: https://canvas.vt.edu/api/v1)")
    args = parser.parse_args()

    # Token resolution
    token = args.token or os.environ.get("CANVAS_TOKEN", "")
    if not token:
        print("ERROR: No token provided. Pass --token or set CANVAS_TOKEN env var.")
        print("Get your token at: https://canvas.vt.edu/profile")
        sys.exit(1)

    print(f"=== Canvas DPO Dataset Generator ===")
    print(f"Handle: {args.handle}")
    print(f"Output: {args.output}")
    print()

    client = CanvasClient(token=token, base_url=args.base_url)

    # Step 1: Fetch
    print("Step 1: Fetching items from Canvas...")
    try:
        raw_items = fetch_items(client)
    except requests.HTTPError as e:
        print(f"HTTP error during fetch: {e}")
        print("Check your token and internet connection.")
        sys.exit(1)
    except Exception as e:
        print(f"Error during fetch: {e}")
        sys.exit(1)

    if not raw_items:
        print("ERROR: No items collected. Is the Canvas URL correct?")
        sys.exit(1)

    # Step 2: Clean
    print("\nStep 2: Cleaning...")
    items = clean(raw_items)
    if not items:
        print("ERROR: No rankable items after cleaning.")
        print("Possible causes: all items already submitted, token has no active courses.")
        sys.exit(1)

    # Step 3: Build course map
    unique_cids = sorted(set(item.course_id for item in items), key=str)
    course_map = {cid: f"COURSE{str(i+1).zfill(3)}" for i, cid in enumerate(unique_cids)}
    print(f"  Courses: {len(course_map)}")

    # Step 4: Pairs
    n = args.n_pairs
    if n is None:
        n = max(100, len(items) * 5)
    print(f"\nStep 3: Generating {n} pairs (seed={args.seed}, min_diff={args.min_diff})...")
    pairs, attempts = generate_pairs(items, n, args.seed, args.min_diff, course_map)
    print(f"  {len(pairs)} pairs from {attempts} attempts")

    # Step 5: Write
    print(f"\nStep 4: Writing to {args.output}...")
    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Step 6: Summary
    print(f"\nDone. {len(pairs)} pairs written.")
    print(f"  Items processed: {len(items)}")
    print(f"  Courses seen: {len(course_map)}")
    print(f"  Course map: {dict(list(course_map.items())[:5])}{'...' if len(course_map) > 5 else ''}")

    # Stats
    d_counts = {"easy": 0, "medium": 0, "hard": 0}
    t_counts = {t: 0 for t in PAIR_TYPES}
    diffs = []
    for p in pairs:
        d_counts[p["difficulty"]] = d_counts.get(p["difficulty"], 0) + 1
        t_counts[p["pair_type"]] = t_counts.get(p["pair_type"], 0) + 1
        diffs.append(p["urgency_diff"])

    import statistics
    print(f"\nStats:")
    print(f"  Urgency diff — mean: {statistics.mean(diffs):.1f}, min: {min(diffs):.1f}, max: {max(diffs):.1f}")
    print(f"  Difficulty: {d_counts}")
    print(f"  Pair types: {t_counts}")

    # Sanity check
    with open(args.output) as f:
        first = json.loads(f.readline())
    label = "item_a" if first["preference"] == 1 else "item_b"
    print(f"\nSample query: {first['query'][:100]}...")
    print(f"  Winner: {label} | diff={first['urgency_diff']} | type={first['pair_type']} | {first['difficulty']}")


if __name__ == "__main__":
    main()