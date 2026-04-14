#!/usr/bin/env python3
"""Generate training data for Canvas item reranker."""
import json, os
from pathlib import Path

SAMPLE_ITEMS = [
    {"key": "sample_001", "ptype": "assignment", "title": "CS 3704 Problem Set 3", "course_code": "CS 3704", "due_iso": "2026-04-10T23:59:00Z", "points": 100.0, "status_flags": ["missing"]},
    {"key": "sample_002", "ptype": "quiz", "title": "NEUR 2464 Quiz 2", "course_code": "NEUR 2464", "due_iso": "2026-04-11T22:00:00Z", "points": 25.0, "status_flags": ["late"]},
    {"key": "sample_003", "ptype": "assignment", "title": "HD 3114 Reading Response", "course_code": "HD 3114", "due_iso": "2026-04-14T23:59:00Z", "points": 15.0, "status_flags": []},
    {"key": "sample_004", "ptype": "exam", "title": "CS 2505 Midterm 2", "course_code": "CS 2505", "due_iso": "2026-04-15T23:59:00Z", "points": 200.0, "status_flags": []},
    {"key": "sample_005", "ptype": "discussion", "title": "NEUR 2464 Discussion", "course_code": "NEUR 2464", "due_iso": "2026-04-17T23:59:00Z", "points": 10.0, "status_flags": []},
    {"key": "sample_006", "ptype": "event", "title": "VT Spring Career Fair", "course_code": "VT", "due_iso": "2026-04-21T09:00:00Z", "points": 0.0, "status_flags": []},
    {"key": "sample_007", "ptype": "assignment", "title": "CS 3704 Lab 4", "course_code": "CS 3704", "due_iso": "2026-04-08T23:59:00Z", "points": 50.0, "status_flags": ["submitted"]},
    {"key": "sample_008", "ptype": "assignment", "title": "HD 3114 Research Summary", "course_code": "HD 3114", "due_iso": "2026-04-19T23:59:00Z", "points": 200.0, "status_flags": []},
    {"key": "sample_009", "ptype": "announcement", "title": "CS 3704 Final Guidelines", "course_code": "CS 3704", "due_iso": "2026-04-16T12:00:00Z", "points": 0.0, "status_flags": []},
    {"key": "sample_010", "ptype": "quiz", "title": "NEUR 2464 fMRI Quiz", "course_code": "NEUR 2464", "due_iso": "2026-04-18T22:00:00Z", "points": 30.0, "status_flags": []},
]

TYPE_SCORES = {"exam": 8, "quiz": 6, "assignment": 4, "discussion": 2, "event": 1, "announcement": 0}
STATUS_SCORES = {"missing": 10, "late": 5, "submitted": -50, "excused": -50}

def compute_urgency(item):
    score = 0.0
    flags = item.get("status_flags", [])
    for f in flags:
        fl = f.lower()
        if fl in STATUS_SCORES:
            score += STATUS_SCORES[fl]
    ptype = item.get("ptype", "").lower()
    for t, s in TYPE_SCORES.items():
        if t in ptype:
            score += s
            break
    try:
        pts = float(item.get("points") or 0)
        score += min(6.0, pts / 50.0)
    except:
        pass
    due_iso = item.get("due_iso", "")
    if due_iso:
        try:
            from datetime import datetime, timezone
            due = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
            due_utc = due.astimezone(timezone.utc)
            now = datetime.now(timezone.utc)
            delta_h = (due_utc - now).total_seconds() / 3600.0
            if delta_h < 0:
                score += max(20, abs(delta_h) * 2)
            elif delta_h < 168:
                score += max(0, (168 - delta_h) / 24) * 2
        except:
            pass
    return max(0.0, score)

def serialize(item):
    ptype = item.get("ptype", "?").lower()
    badge = {"assignment": "ASGN", "quiz": "QUIZ", "exam": "EXAM", "discussion": "DISC", "event": "EVNT", "announcement": "NOTE"}.get(ptype, ptype[:4].upper())
    title = (item.get("title") or "(untitled)")[:40]
    code = item.get("course_code", "")
    parts = [f"[{badge}] {title}"]
    if code:
        parts[0] += f" @{code}"
    due = item.get("due_iso", "")
    if due:
        parts[0] += f" due:{due[:10]}"
    pts = item.get("points", 0)
    if pts:
        parts[0] += f" {pts:.0f}pts"
    return parts[0]

QUERIES = ["due soon", "all items", "upcoming", "high priority", "check grades"]

pairs = []
scored = [(compute_urgency(it), it) for it in SAMPLE_ITEMS]
scored.sort(key=lambda x: -x[0])

seen = set()
for i, (sa, a) in enumerate(scored):
    for sb, b in scored[i+1:]:
        ka = a["key"]
        kb = b["key"]
        pk = (min(ka, kb), max(ka, kb))
        if pk in seen:
            continue
        seen.add(pk)
        pref = 1 if sa >= sb else 0
        reason = f"urgency {sa:.1f} vs {sb:.1f}"
        for q in QUERIES:
            pairs.append({"query": q, "item_a": serialize(a), "item_b": serialize(b), "preference": pref, "urgency_a": round(sa, 2), "urgency_b": round(sb, 2), "reason": reason})

# also general
for a, b in [(scored[i][1], scored[j][1]) for i in range(len(scored)) for j in range(i+1, len(scored))]:
    pairs.append({"query": "all items", "item_a": serialize(a), "item_b": serialize(b), "preference": 1 if compute_urgency(a) >= compute_urgency(b) else 0, "urgency_a": round(compute_urgency(a), 2), "urgency_b": round(compute_urgency(b), 2), "reason": "general urgency"})

Path("data").mkdir(exist_ok=True)
with open("data/rerank_train.jsonl", "w") as f:
    for p in pairs:
        f.write(json.dumps(p) + "\n")

print(f"Wrote {len(pairs)} pairs")
for p in pairs[:3]:
    print(f"  [{p['preference']}] A={p['urgency_a']} B={p['urgency_b']} | {p['item_a'][:40]} vs {p['item_b'][:40]}")