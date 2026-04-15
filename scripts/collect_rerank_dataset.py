#!/usr/bin/env python3
"""
Canvas Priority Reranker — Collaborative Dataset Collection
==========================================================
Each teammate runs this locally with their own Canvas API token.
Pulls real Canvas items, generates pairwise ranking pairs, outputs JSONL.

PRIVACY: Use --anonymize to strip identifying info before sharing.
See DATASET_README.md for full teammate contribution workflow.

Usage:
    # Setup token (once per machine)
    export CANVAS_TOKEN="your_canvas_token"
    export CANVAS_BASE_URL="https://canvas.vt.edu"

    # Generate your private data
    python3 scripts/collect_rerank_dataset.py generate \
        --output data/collab/YOUR_HANDLE.jsonl --handle YOUR_HANDLE

    # ANONYMIZE before contributing (REQUIRED)
    python3 scripts/collect_rerank_dataset.py anonymize \
        --input data/collab/YOUR_HANDLE.jsonl \
        --output data/collab/YOUR_HANDLE_anon.jsonl

    # Merge + clean + split + export
    python3 scripts/collect_rerank_dataset.py merge data/collab/*_anon.jsonl \
        --output data/collab/rerank_merged.jsonl
    python3 scripts/collect_rerank_dataset.py clean \
        --input data/collab/rerank_merged.jsonl \
        --output data/collab/rerank_clean.jsonl
    python3 scripts/collect_rerank_dataset.py split \
        --input data/collab/rerank_clean.jsonl \
        --train data/rerank_train.jsonl \
        --test data/rerank_test.jsonl
    python3 scripts/collect_rerank_dataset.py export-sft \
        --input data/rerank_train.jsonl \
        --output data/rerank_sft.jsonl
    python3 scripts/collect_rerank_dataset.py export-dpo \
        --input data/rerank_train.jsonl \
        --output data/rerank_dpo.jsonl
"""

import argparse, hashlib, json, os, random, subprocess, sys, textwrap, uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Canvas API ────────────────────────────────────────────────────────────────

TOKEN_FILE   = Path.home() / ".canvas_token"
CANVAS_API   = Path.home() / ".openclaw/hooks/canvas-api.sh"

# ── Heuristic weights (MUST be consistent with benchmark.py) ─────────────────

W_TIME   = 3.0
W_TYPE   = 2.5
W_POINTS = 1.5
W_STATUS = 2.0

CANCELED_TYPES = {"discussion_topic", "quiz", "exam", "midterm", "final"}
COURSE_CODE_OVERRIDES = {}
CANVAS_COURSE_IDS = {}

# ── Helpers ─────────────────────────────────────────────────────────────────

def get_token() -> str | None:
    token = os.environ.get("CANVAS_TOKEN")
    if token: return token
    token = os.environ.get("CANVAS_API_TOKEN")
    if token: return token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None

def canvas_api(subpath: str) -> list[dict]:
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
        sys.exit("Canvas API error: " + result.stderr[-200:])
    return json.loads(result.stdout)

def _hours_until(due_iso: str) -> float:
    if not due_iso: return 999.0
    try:
        due = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
        return (due - datetime.now(timezone.utc)).total_seconds() / 3600.0
    except Exception:
        return 999.0

def _due_label(hours: float) -> str:
    if hours < 0:   return "Overdue " + str(int(abs(hours))) + "h"
    if hours < 1:   return "<1h"
    if hours < 24:  return str(int(hours)) + "h"
    if hours < 168: return str(int(hours / 24)) + "d"
    return str(int(hours / 168)) + "w"

def _type_weight(t: str) -> float:
    t = t.lower()
    if any(k in t for k in CANCELED_TYPES): return 1.0
    if "homework" in t or "assignment" in t: return 0.7
    if "project" in t: return 0.5
    if "reading" in t or "note" in t: return 0.2
    return 0.4

def _type_badge(t: str) -> str:
    t = (t or "").lower()
    if any(k in t for k in CANCELED_TYPES): return "[!]"
    if "homework" in t or "assignment" in t: return "[=]"
    if "project" in t: return "[P]"
    if "quiz" in t: return "[?]"
    return "[*]"

def _urgency(item: dict) -> float:
    h = item.get("hours_until_due", 999)
    return round(
        W_TIME   * (1.0 / max(h, 0.1) ** 0.5)
        + W_TYPE   * _type_weight(item.get("type", ""))
        + W_POINTS * (min(float(item.get("points_possible") or 0), 200) / 200.0)
        + W_STATUS * (0.0 if item.get("has_submitted_submissions") else 1.0),
        4,
    )

def serialize_item(item: dict) -> str:
    hours = item.get("hours_until_due", 999)
    due_lbl = _due_label(hours)
    badge   = _type_badge(item.get("type", ""))
    title   = (item.get("name") or item.get("title") or "Unknown")[:50]
    course  = CANVAS_COURSE_IDS.get(item.get("course_id", 0), str(item.get("course_id", "")))
    pts     = item.get("points_possible") or 0
    status  = "DONE" if item.get("has_submitted_submissions") else ("MISSING" if hours < 0 else "OPEN")
    return badge + " " + title + " \u2014 " + course + " \u2014 " + due_lbl + " \u2014 " + str(int(pts)) + "pts \u2014 " + status

def _anon_course(cid: int) -> str:
    h = int(hashlib.md5(str(cid).encode()).hexdigest()[:6], 16)
    return "COURSE" + str((h % 999) + 1).zfill(3)

def _anon_title(item_type: str) -> str:
    t = (item_type or "").lower()
    if "homework" in t or "assignment" in t: return "Homework"
    if "quiz" in t: return "Quiz"
    if any(k in t for k in ["exam","midterm","final"]): return "Exam"
    if "project" in t: return "Project"
    if "reading" in t: return "Reading"
    return "Assignment"

def _serialize_anon(item: dict, course_map: dict[int,str]) -> str:
    hours  = item.get("hours_until_due", 999)
    badge  = _type_badge(item.get("type", ""))
    title  = _anon_title(item.get("type", ""))
    cid    = item.get("course_id", 0)
    course = course_map.get(cid, _anon_course(cid))
    pts    = item.get("points_possible") or 0
    status = "DONE" if item.get("has_submitted_submissions") else ("MISSING" if hours < 0 else "OPEN")
    return badge + " " + title + " \u2014 " + course + " \u2014 " + _due_label(hours) + " \u2014 " + str(int(pts)) + "pts \u2014 " + status

# ── Pair generation ──────────────────────────────────────────────────────────

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

def generate_pairs(items: list[dict], handle: str) -> list[dict]:
    pairs = []
    for i, item_a in enumerate(items):
        for item_b in items[i + 1:]:
            ua, ub = item_a["urgency"], item_b["urgency"]
            difficulty = abs(ua - ub)
            pref = 1 if ua >= ub else 0
            winner = "A" if pref == 1 else "B"
            pairs.append({
                "id":         str(uuid.uuid4())[:8],
                "query":      random.choice(QUERY_TEMPLATES),
                "item_a":     {k: v for k, v in item_a.items() if not k.startswith("_")},
                "item_b":     {k: v for k, v in item_b.items() if not k.startswith("_")},
                "preference": pref,
                "urgency_a":  ua,
                "urgency_b":  ub,
                "reason":     "Item " + winner + " has higher urgency (" + winner + "=" + str(ua) + " vs " + ("B" if winner=="A" else "A") + "=" + str(ub) + ", diff=" + str(round(difficulty,1)) + ")",
                "pair_type":  "hard_negative" if difficulty < 3.0 else "standard",
                "source_user": handle,
            })
    prefs = {1: [], 0: []}
    for p in pairs: prefs[p["preference"]].append(p)
    min_c = min(len(prefs[1]), len(prefs[0]))
    pairs = prefs[1][:min_c] + prefs[0][:min_c]
    random.shuffle(pairs)
    return pairs

def deduplicate_pairs(pairs: list[dict]) -> list[dict]:
    seen = {}
    for p in pairs:
        key = tuple(sorted([str(p["item_a"].get("id","")), str(p["item_b"].get("id",""))]))
        if key not in seen or len(p.get("signals",[])) > len(seen.get(key,{}).get("signals",[])):
            seen[key] = p
    return list(seen.values())

def balance_preferences(pairs: list[dict]) -> list[dict]:
    prefs = {1: [], 0: []}
    for p in pairs: prefs[p["preference"]].append(p)
    min_c = min(len(prefs[1]), len(prefs[0]))
    balanced = prefs[1][:min_c] + prefs[0][:min_c]
    random.shuffle(balanced)
    return balanced

# ── Format functions ─────────────────────────────────────────────────────────

def format_for_sft(pairs: list[dict], anonymize: bool = False,
                   course_map: dict|None = None) -> list[dict]:
    formatted = []
    for p in pairs:
        pref = "A" if p["preference"] == 1 else "B"
        if anonymize and course_map:
            item_a_ser = _serialize_anon(p["item_a"], course_map)
            item_b_ser = _serialize_anon(p["item_b"], course_map)
        elif anonymize:
            item_a_ser = _serialize_anon(p["item_a"], {p["item_a"].get("course_id",0): _anon_course(p["item_a"].get("course_id",0))})
            item_b_ser = _serialize_anon(p["item_b"], {p["item_b"].get("course_id",0): _anon_course(p["item_b"].get("course_id",0))})
        else:
            item_a_ser = serialize_item(p["item_a"])
            item_b_ser = serialize_item(p["item_b"])
        text = (
            "[Query]: " + p["query"] + "\n"
            "Item A: " + item_a_ser + "\n"
            "Item B: " + item_b_ser + "\n"
            "Which is more urgent? Item " + pref + " is more urgent.\n"
            "Reason: " + p["reason"] + "<eos>"
        )
        formatted.append({"text": text, "id": p.get("id",""), "pair_type": p.get("pair_type","standard"), "source_user": p.get("source_user","unknown")})
    return formatted

def format_for_dpo(pairs: list[dict]) -> list[dict]:
    formatted = []
    for p in pairs:
        pref = p["preference"]
        winner = "A" if pref == 1 else "B"
        loser  = "B" if pref == 1 else "A"
        prompt = (
            "Which Canvas item is more urgent and why?\n\n"
            "[Query]: " + p["query"] + "\n"
            "Item A: " + serialize_item(p["item_a"]) + "\n"
            "Item B: " + serialize_item(p["item_b"])
        )
        chosen   = "Item " + winner + " is more urgent. " + p["reason"]
        rejected = "Item " + loser + " is less urgent."
        formatted.append({
            "prompt": prompt, "chosen": chosen, "rejected": rejected,
            "id": p.get("id",""), "pair_type": p.get("pair_type","standard"),
            "source_user": p.get("source_user","unknown"),
        })
    return formatted

# ── Anonymization ──────────────────────────────────────────────────────────

def anonymize_pairs(pairs: list[dict], output_path: str) -> list[dict]:
    all_cids = set()
    for p in pairs:
        all_cids.add(p["item_a"].get("course_id", 0))
        all_cids.add(p["item_b"].get("course_id", 0))
    course_map = {cid: "COURSE" + str(i+1).zfill(3) for i, cid in enumerate(sorted(all_cids))}
    seen_users, next_c = {}, 1
    anon_pairs = []
    for p in pairs:
        ou = p.get("source_user","unknown")
        if ou not in seen_users:
            seen_users[ou] = "contributor" + str(next_c).zfill(3)
            next_c += 1
        item_a = {"type": p["item_a"].get("type","assignment"), "points_possible": p["item_a"].get("points_possible",0),
                  "has_submitted_submissions": p["item_a"].get("has_submitted_submissions",False),
                  "hours_until_due": p["item_a"].get("hours_until_due", 999),
                  "course_code": course_map.get(p["item_a"].get("course_id",0),"COURSE001"),
                  "serialized": _serialize_anon(p["item_a"], course_map)}
        item_b = {"type": p["item_b"].get("type","assignment"), "points_possible": p["item_b"].get("points_possible",0),
                  "has_submitted_submissions": p["item_b"].get("has_submitted_submissions",False),
                  "hours_until_due": p["item_b"].get("hours_until_due", 999),
                  "course_code": course_map.get(p["item_b"].get("course_id",0),"COURSE001"),
                  "serialized": _serialize_anon(p["item_b"], course_map)}
        anon_pairs.append({
            "id": str(uuid.uuid4())[:8], "query": p["query"],
            "item_a": item_a, "item_b": item_b,
            "preference": p["preference"], "urgency_a": p["urgency_a"], "urgency_b": p["urgency_b"],
            "reason": p["reason"], "pair_type": p.get("pair_type","standard"),
            "source_user": seen_users[ou], "_anon": True,
        })
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for p_item in anon_pairs:
            f.write(json.dumps(p_item) + "\n")
    print("[ANON] " + str(len(anon_pairs)) + " pairs | " + str(len(course_map)) + " courses -> COURSE001-COURSE" + str(len(course_map)).zfill(3) + " | " + str(len(seen_users)) + " contributors")
    print("[ANON] Wrote: " + str(out))
    return anon_pairs

# ── CLI commands ─────────────────────────────────────────────────────────────

def cmd_setup(args):
    token = args.token or input("Canvas API token: ").strip()
    if not token: sys.exit("Token required.")
    base = os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu")
    result = subprocess.run([str(CANVAS_API), "courses"], capture_output=True, text=True,
                           env={**os.environ, "CANVAS_TOKEN": token, "CANVAS_BASE_URL": base})
    if result.returncode != 0: sys.exit("Token verification failed: " + result.stderr[-200:])
    zshenv = Path.home() / ".zshenv"
    existing = zshenv.read_text() if zshenv.exists() else ""
    lines = [l for l in existing.splitlines() if not l.startswith("export CANVAS_TOKEN=")]
    lines.append('export CANVAS_TOKEN="' + token + '"')
    lines.append('export CANVAS_BASE_URL="https://canvas.vt.edu"')
    zshenv.write_text("\n".join(lines) + "\n")
    print("[OK] Token written to ~/.zshenv")
    TOKEN_FILE.write_text(token); TOKEN_FILE.chmod(0o600)
    print("[OK] Token also saved to " + str(TOKEN_FILE) + " (legacy)")

def cmd_generate(args):
    global CANVAS_COURSE_IDS
    token = get_token()
    if not token: sys.exit("ERROR: Set CANVAS_TOKEN env var")
    print("Fetching courses...")
    courses = canvas_api("courses")
    CANVAS_COURSE_IDS = {c.get("id"): COURSE_CODE_OVERRIDES.get(c.get("id")) or c.get("course_code","COURSE"+str(c.get("id") or "")[-3:]) for c in courses}
    if args.courses:
        for cid in args.courses:
            CANVAS_COURSE_IDS[cid] = CANVAS_COURSE_IDS.get(cid, "COURSE"+str(cid%999))
    all_items = []
    for cid in CANVAS_COURSE_IDS:
        items = canvas_api("courses/" + str(cid) + "/items")
        for item in items:
            item["course_id"] = cid
            item["course_name"] = next((c.get("name","") for c in courses if c.get("id")==cid), "")
        all_items.extend(items)
    seen = {}
    for item in all_items:
        iid = item.get("id")
        if iid and (iid not in seen or len(item.get("submission",{}).get("attachments",[])) > 0):
            seen[iid] = item
    items = list(seen.values())
    for item in items:
        item["hours_until_due"] = _hours_until(item.get("due_at",""))
        item["urgency"] = _urgency(item)
    print("  " + str(len(items)) + " unique items from " + str(len(CANVAS_COURSE_IDS)) + " courses")
    pairs = generate_pairs(items, args.handle)
    print("  " + str(len(pairs)) + " pairs generated")
    pairs = balance_preferences(deduplicate_pairs(pairs))
    print("  " + str(len(pairs)) + " after dedup + balance")
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for p in pairs: f.write(json.dumps(p) + "\n")
    print("[OK] Wrote: " + str(out) + " (" + str(out.stat().st_size//1024) + "KB)")
    print("     Next: anonymize then submit to team")

def cmd_merge(args):
    import glob
    files = []
    for pattern in args.files: files.extend(glob.glob(str(pattern)))
    files = sorted(set(files))
    all_pairs, seen = [], set()
    for f in files:
        for line in open(f):
            line = line.strip()
            if not line: continue
            p = json.loads(line)
            key = (str(p.get("id","")), str(p.get("source_user","")))
            if key not in seen:
                seen.add(key); all_pairs.append(p)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for p in all_pairs: f.write(json.dumps(p) + "\n")
    print("[OK] Merged: " + str(len(files)) + " files -> " + str(len(all_pairs)) + " pairs -> " + str(out))

def cmd_clean(args):
    pairs = [json.loads(l) for l in open(args.input) if l.strip()]
    print("Loaded: " + str(len(pairs)))
    pairs = balance_preferences(deduplicate_pairs(pairs))
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for p in pairs: f.write(json.dumps(p) + "\n")
    print("[OK] Cleaned: " + str(len(pairs)) + " pairs -> " + str(out))
    pref1 = sum(1 for p in pairs if p.get("preference")==1)
    print("     Balance: A=" + str(pref1) + ", B=" + str(len(pairs)-pref1))

def cmd_split(args):
    import random
    pairs = [json.loads(l) for l in open(args.input) if l.strip()]
    random.seed(args.seed)
    hard_neg = [p for p in pairs if p.get("pair_type")=="hard_negative"]
    standard = [p for p in pairs if p.get("pair_type")!="hard_negative"]
    def split_group(lst, frac):
        random.shuffle(lst)
        n = max(1, int(len(lst)*frac))
        return lst[:n], lst[n:]
    train_hn, test_hn = split_group(hard_neg, 1-args.test_frac)
    train_std, test_std = split_group(standard, 1-args.test_frac)
    train = train_hn + train_std; test = test_hn + test_std
    random.shuffle(train); random.shuffle(test)
    print("[SPLIT] Total: " + str(len(pairs)) + " | HardNeg: " + str(len(hard_neg)) + " | Standard: " + str(len(standard)))
    print("[SPLIT] Train: " + str(len(train)) + " | Test: " + str(len(test)))
    for label, data in [("train", train), ("test", test)]:
        p = Path(args.train if label=="train" else args.test)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            for item in data: f.write(json.dumps(item) + "\n")
        print("[SPLIT] Wrote: " + str(p) + " (" + str(p.stat().st_size//1024) + "KB)")

def cmd_expand_benchmark(args):
    """Add 12 new adversarial/edge-case query types to existing test data."""
    new_queries = [
        "Which is a last-minute emergency?",
        "What would a professor expect me to prioritize?",
        "Which assignment is worth the most relative to others?",
        "What can I safely skip if I run out of time?",
        "Which item has no submission yet and is long overdue?",
        "What's the highest-value task I should start?",
        "Which exam is most imminent?",
        "What requires the most time to complete?",
        "What's closing soon and worth significant points?",
        "What has the lowest urgency but highest grade impact?",
        "Which assignment has the strictest type urgency?",
        "What should I tackle after 10pm?",
    ]
    pairs = [json.loads(l) for l in open(args.input) if l.strip()]
    new_pairs = []
    for qi, query in enumerate(new_queries):
        count = 0
        for pi, pair in enumerate(pairs):
            if pi % len(new_queries) == qi % len(pairs):
                new_pair = dict(pair)
                new_pair["id"] = f"exp{qi:02d}_{pi:04d}"
                new_pair["query"] = query
                new_pair["pair_type"] = "expanded_adversarial"
                new_pairs.append(new_pair)
                count += 1
                if count >= 16:  # ~16 pairs per new query for even distribution
                    break
    all_pairs = pairs + new_pairs
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for p in all_pairs: f.write(json.dumps(p) + "\n")
    q_counts = {}
    for p in all_pairs:
        q = p["query"]; q_counts[q] = q_counts.get(q, 0) + 1
    print("[EXPAND] +" + str(len(new_pairs)) + " pairs across " + str(len(new_queries)) + " queries -> " + str(args.output))
    print("[EXPAND] Total: " + str(len(all_pairs)) + " pairs | " + str(len(q_counts)) + " unique queries")
    for q, c in sorted(q_counts.items(), key=lambda x: -x[1]):
        print("  [" + str(c) + "] " + q)

def cmd_anonymize(args):
    pairs = [json.loads(l) for l in open(args.input) if l.strip()]
    print("[ANON] Loaded: " + str(len(pairs)) + " pairs")
    anonymize_pairs(pairs, args.output)

def cmd_export_sft(args):
    pairs = [json.loads(l) for l in open(args.input) if l.strip()]
    course_map = None
    if getattr(args, "anonymize", False):
        all_cids = set()
        for p in pairs:
            all_cids.add(p["item_a"].get("course_id",0)); all_cids.add(p["item_b"].get("course_id",0))
        course_map = {cid: "COURSE"+str(i+1).zfill(3) for i, cid in enumerate(sorted(all_cids))}
    formatted = format_for_sft(pairs, anonymize=getattr(args,"anonymize",False), course_map=course_map)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for p_item in formatted: f.write(json.dumps(p_item) + "\n")
    tag = " (anonymized)" if getattr(args,"anonymize",False) else ""
    print("[SFT] Wrote: " + str(out) + " (" + str(len(formatted)) + " examples)" + tag)

def cmd_export_dpo(args):
    pairs = [json.loads(l) for l in open(args.input) if l.strip()]
    formatted = format_for_dpo(pairs)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for p_item in formatted: f.write(json.dumps(p_item) + "\n")
    pref1 = sum(1 for p in pairs if p.get("preference")==1)
    print("[DPO] Wrote: " + str(out) + " (" + str(len(formatted)) + " examples)")
    print("[DPO] Preferences — A: " + str(pref1) + ", B: " + str(len(pairs)-pref1))

# ── CLI parser ──────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Canvas Priority Reranker — Collaborative Dataset Collection")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="Save Canvas API token to ~/.zshenv")
    s.add_argument("--token"); s.set_defaults(fn=cmd_setup)

    g = sub.add_parser("generate", help="Pull Canvas items -> pairwise dataset")
    g.add_argument("--output", required=True); g.add_argument("--handle", required=True)
    g.add_argument("--courses", nargs="+", type=int); g.set_defaults(fn=cmd_generate)

    m = sub.add_parser("merge", help="Merge multiple JSONL files")
    m.add_argument("files", nargs="+"); m.add_argument("--output", required=True); m.set_defaults(fn=cmd_merge)

    c = sub.add_parser("clean", help="Deduplicate + balance")
    c.add_argument("--input", required=True); c.add_argument("--output", required=True); c.set_defaults(fn=cmd_clean)

    sp = sub.add_parser("split", help="Stratified train/test split")
    sp.add_argument("--input", required=True)
    sp.add_argument("--train", default="data/rerank_train.jsonl")
    sp.add_argument("--test", default="data/rerank_test.jsonl")
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--test-frac", type=float, default=0.1)
    sp.set_defaults(fn=cmd_split)

    ep = sub.add_parser("expand-benchmark", help="Add new query types to test set for richer benchmarks")
    ep.add_argument("--input", required=True, help="Existing test set")
    ep.add_argument("--output", required=True, help="Expanded output path")
    ep.set_defaults(fn=cmd_expand_benchmark)

    a = sub.add_parser("anonymize", help="Anonymize for safe publication")
    a.add_argument("--input", required=True); a.add_argument("--output", required=True); a.set_defaults(fn=cmd_anonymize)

    sf = sub.add_parser("export-sft", help="Export to SFTTrainer JSONL format")
    sf.add_argument("--input", required=True); sf.add_argument("--output", required=True)
    sf.add_argument("--anonymize", action="store_true"); sf.set_defaults(fn=cmd_export_sft)

    dp = sub.add_parser("export-dpo", help="Export to DPO format for Path B distillation")
    dp.add_argument("--input", required=True); dp.add_argument("--output", required=True); dp.set_defaults(fn=cmd_export_dpo)

    args = p.parse_args()
    args.fn(args)

if __name__ == "__main__": parse_args()
