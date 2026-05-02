"""
collect_trajectories.py — teammate-runnable v2 trajectory collector.

Purpose: build the v2 calendar-agent training dataset by replaying a fixed
set of canonical user queries against a teacher LLM (Nemotron-120B at
Spark slot0:18080 by default) with the canvas-tui agent's tool surface
exposed for function-calling. Captures the full tool-call trajectory
(tool calls + tool results + final answer) per query.

This is the v2 analogue of the v1 generate_dataset.py / collect_rerank_
dataset.py preference collectors. Same anonymization pipeline; same
multi-contributor model.

Usage (from canvas-tui repo root, with canvas_sdk installed and a
Canvas API token in your env):

    export CANVAS_TOKEN=...
    export CANVAS_BASE_URL=https://canvas.vt.edu
    export TEACHER_ENDPOINT=http://spark.local:18080/v1   # optional
    python3 GemmaReranker/scripts/collect_trajectories.py \
        --contributor alice \
        --queries GemmaReranker/data/canonical_queries.txt \
        --output GemmaReranker/data/collab/alice_trajectories.jsonl \
        --max-trajectories 50

The output JSONL is the v2 SFT corpus. Each line is one trajectory:
    {user_query, context, trajectory[], teacher_model, contributor_id}

Contributors push their anonymized JSONL to GemmaReranker/data/collab/
in a PR; the maintainer concatenates + further audits before training.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# ── Tool surface (mirrors canvas_tui.agent.tools registry) ───────────────────

TOOL_SCHEMAS: list[dict] = []  # populated lazily by import


def _import_tools():
    """Lazy-import the agent tool registry. Falls back to a minimal
    schema set if canvas_tui isn't installed (so contributors without
    the full app can still produce stub trajectories)."""
    global TOOL_SCHEMAS
    try:
        from canvas_tui.agent.tools import get_schemas  # type: ignore
        TOOL_SCHEMAS = get_schemas()
        return True
    except ImportError:
        TOOL_SCHEMAS = _minimal_tool_schemas()
        return False


def _minimal_tool_schemas() -> list[dict]:
    """Standalone copy of the tool schemas — keeps this script runnable
    even when canvas_tui isn't on the PYTHONPATH (e.g. teammate has
    only cloned GemmaReranker/ standalone)."""
    return [
        {"type": "function", "function": {
            "name": "canvas.list_courses",
            "description": "List the student's enrolled courses.",
            "parameters": {"type": "object", "properties": {"active_only": {"type": "boolean"}}},
        }},
        {"type": "function", "function": {
            "name": "canvas.get_assignments",
            "description": "Get assignments per course.",
            "parameters": {"type": "object", "properties": {
                "course_id": {"type": ["integer", "null"]},
                "horizon_days": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "canvas.get_todo",
            "description": "Get the Canvas TODO feed.",
            "parameters": {"type": "object", "properties": {}},
        }},
        {"type": "function", "function": {
            "name": "canvas.get_syllabus",
            "description": "Get a course's syllabus text.",
            "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]},
        }},
        {"type": "function", "function": {
            "name": "calendar.list_events",
            "description": "List calendar events in a window.",
            "parameters": {"type": "object", "properties": {
                "start_iso": {"type": "string"}, "end_iso": {"type": "string"},
            }},
        }},
        {"type": "function", "function": {
            "name": "calendar.find_free_blocks",
            "description": "Find free blocks of time.",
            "parameters": {"type": "object", "properties": {
                "min_minutes": {"type": "integer"}, "horizon_days": {"type": "integer"},
            }},
        }},
        {"type": "function", "function": {
            "name": "calendar.create_event",
            "description": "Create a calendar event.",
            "parameters": {"type": "object", "properties": {
                "title": {"type": "string"}, "start_iso": {"type": "string"}, "end_iso": {"type": "string"},
            }, "required": ["title", "start_iso", "end_iso"]},
        }},
        {"type": "function", "function": {
            "name": "study.spaced_schedule",
            "description": "Compute spaced-repetition session dates for an exam (Cepeda 2008).",
            "parameters": {"type": "object", "properties": {
                "exam_iso": {"type": "string"}, "n_sessions": {"type": "integer"},
            }, "required": ["exam_iso"]},
        }},
        {"type": "function", "function": {
            "name": "study.recommend_block_size",
            "description": "Recommend deep-work block size for a task type.",
            "parameters": {"type": "object", "properties": {
                "task_type": {"type": "string", "enum": ["writing","problem_set","exam_prep","reading","review","admin","discussion","project_work"]},
            }, "required": ["task_type"]},
        }},
    ]


# ── Canonical queries (default; --queries file overrides) ────────────────────

CANONICAL_QUERIES = [
    # 1. Exam prep — neuroscience-grounded spacing
    "I have a CS3704 midterm in 12 days. Plan my prep using spaced repetition.",
    "I have a final exam on May 15. What should my prep schedule look like?",
    "How should I structure my study time for two midterms in the same week?",
    # 2. Realistic week — multi-source planning
    "I have 5 things due this week and a 6-hour shift on Saturday. What's the realistic schedule?",
    "I have a doctor's appointment Tuesday and a quiz Wednesday. When do I prep?",
    "Walk me through my upcoming week with specific time blocks.",
    # 3. Project-only courses
    "My software engineering class only has a final project. When should I work on it?",
    "I have a 4-credit class with one big group project due in 6 weeks. Allocate weekly time.",
    # 4. Priority queries
    "What's most urgent right now?",
    "What can I safely skip this week if I run out of time?",
    "Which assignments are highest grade impact?",
    # 5. Edge cases
    "I'm overwhelmed. Where do I start?",
    "I have 3 assignments due tomorrow. Triage.",
    "What did I miss this week?",
    # 6. Recovery / rescheduling
    "I'm sick and missed two days. Reschedule everything.",
    "An exam got moved up by a week. Replan.",
    # 7. Life balance
    "Block time for the gym 3x this week without breaking my study schedule.",
    "When can I realistically take Friday night off?",
]


# ── Anonymization (mirrors GemmaReranker/scripts/scrub.py) ───────────────────

def anonymize_course_code(real_code: str) -> str:
    """Same SHA-256 → 4-digit modulo as canvas-tui agent's serialize_item.
    Deterministic per real code, so contributors with overlapping courses
    produce identical anonymized codes."""
    h = int(hashlib.sha256(real_code.strip().encode("utf-8")).hexdigest()[:8], 16)
    return f"COURSE{(h % 9000) + 1000}"


def anonymize_record(rec: dict, contributor_salt: str) -> dict:
    """Walk a trajectory record, replace real course codes / Canvas IDs /
    contributor PII with deterministic anonymized stand-ins. Contributor-
    salt makes IDs non-overlapping across contributors."""
    text = json.dumps(rec, default=str)
    # Replace anything matching a 7-9 digit Canvas ID with a SHA-prefixed stub.
    import re
    text = re.sub(r"\b([1-9]\d{6,8})\b",
                  lambda m: f"ID{int(hashlib.sha256((contributor_salt + m.group(1)).encode()).hexdigest()[:6], 16) % 1000000:06d}",
                  text)
    # Real course codes like "CS 3704", "ENGL 2204" → anonymized.
    text = re.sub(r"\b([A-Z]{2,5})\s*(\d{3,4}[A-Z]?)\b",
                  lambda m: anonymize_course_code(m.group(0)),
                  text)
    return json.loads(text)


# ── Teacher interaction (Nemotron-120B at slot0:18080 by default) ────────────

def call_teacher(messages: list[dict], tools: list[dict], endpoint: str, model: str) -> dict:
    """Make one tool-aware call to the teacher. Returns the full response
    (including tool_calls if the model decided to call tools, or content
    if it decided to answer)."""
    import requests
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.2,  # low but not zero — diversity for plan candidates
        "max_tokens": 1024,
    }
    r = requests.post(f"{endpoint}/chat/completions", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


# ── Mock tool executor — for trajectory capture, we don't actually mutate
# the calendar; we synthesize plausible results from the contributor's
# Canvas snapshot. Real execution happens at deploy time.
def execute_tool(name: str, args: dict, snapshot: dict) -> Any:
    """Minimal mock — returns plausible-looking results for trajectory
    capture without actually calling Canvas/calendar APIs at collection
    time. The teacher's reasoning + tool-call sequence is what we capture;
    the tool-result content is regenerated at training time from the
    snapshot to keep the trajectory deterministic."""
    if name == "canvas.list_courses":
        return snapshot.get("courses", [])
    if name == "canvas.get_assignments":
        cid = args.get("course_id")
        items = snapshot.get("assignments", [])
        if cid is not None:
            items = [a for a in items if a.get("course_id") == cid]
        horizon = args.get("horizon_days", 14)
        cutoff = (dt.datetime.now() + dt.timedelta(days=horizon)).isoformat()
        return [a for a in items if a.get("due_iso", "9999") <= cutoff]
    if name == "canvas.get_todo":
        return snapshot.get("todo", [])
    if name == "canvas.get_syllabus":
        cid = args.get("course_id")
        return snapshot.get("syllabi", {}).get(str(cid), "(no syllabus on file)")
    if name == "calendar.list_events":
        return snapshot.get("calendar_events", [])
    if name == "calendar.find_free_blocks":
        # Synthesize plausible free blocks based on calendar density
        return [
            {"start_iso": (dt.datetime.now() + dt.timedelta(days=d, hours=9)).isoformat(),
             "end_iso":   (dt.datetime.now() + dt.timedelta(days=d, hours=10, minutes=30)).isoformat()}
            for d in range(1, 1 + args.get("horizon_days", 7))
        ]
    if name == "calendar.create_event":
        return {"event_id": f"mock-{abs(hash(json.dumps(args, sort_keys=True)))}", "status": "created"}
    if name == "study.spaced_schedule":
        # Use the canvas-tui implementation if available
        try:
            from canvas_tui.agent.tools.study_tools import SpacedSchedule
            return SpacedSchedule.call(args)
        except ImportError:
            return [{"start_iso": "...", "end_iso": "..."}]
    if name == "study.recommend_block_size":
        try:
            from canvas_tui.agent.tools.study_tools import DeepBlockSize
            return DeepBlockSize.call(args)
        except ImportError:
            return {"minutes": 90, "rationale": "default deep-work block"}
    return {"error": f"unknown tool: {name}"}


# ── Trajectory loop ──────────────────────────────────────────────────────────

def collect_one(query: str, snapshot: dict, contributor_id: str,
                endpoint: str, model: str, max_calls: int = 12) -> dict:
    """Run one query through the teacher with tool calls, capturing the
    full trajectory. Returns the trajectory record."""
    sys_prompt = Path(__file__).parent.parent.parent / "src/canvas_tui/agent/prompts/system.md"
    if sys_prompt.exists():
        system = sys_prompt.read_text()
    else:
        system = "You are a personal AI calendar + study assistant. Use tool calls when you need data."
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]
    trajectory = []
    for step in range(max_calls):
        resp = call_teacher(messages, TOOL_SCHEMAS, endpoint, model)
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            for tc in tool_calls:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                trajectory.append({"role": "assistant", "tool_call": {"name": name, "args": args}})
                result = execute_tool(name, args, snapshot)
                trajectory.append({"role": "tool", "name": name, "result": result})
                messages.append({"role": "assistant", "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": name, "content": json.dumps(result, default=str)})
        elif msg.get("content"):
            trajectory.append({"role": "assistant", "final_answer": msg["content"]})
            return {
                "user_query": query,
                "context": {"now_iso": dt.datetime.now().isoformat(), "snapshot_keys": list(snapshot.keys())},
                "trajectory": trajectory,
                "teacher_model": model,
                "contributor_id": contributor_id,
            }
        else:
            break
    trajectory.append({"role": "assistant", "final_answer": "(max tool calls reached without final answer)"})
    return {
        "user_query": query,
        "context": {"now_iso": dt.datetime.now().isoformat(), "snapshot_keys": list(snapshot.keys())},
        "trajectory": trajectory,
        "teacher_model": model,
        "contributor_id": contributor_id,
        "incomplete": True,
    }


def load_snapshot(contributor: str) -> dict:
    """Load a contributor's Canvas + calendar snapshot. Defers to
    canvas_sdk live fetch if available; falls back to a hand-curated
    snapshot file at GemmaReranker/data/snapshots/<contributor>.json."""
    snapshot_path = Path(f"GemmaReranker/data/snapshots/{contributor}.json")
    if snapshot_path.exists():
        return json.loads(snapshot_path.read_text())
    # Try live fetch via canvas_sdk
    try:
        from canvas_tui.api import CanvasAPI
        api = CanvasAPI.from_config()
        return {
            "courses": [c.to_dict() for c in api.list_courses()],
            "assignments": [a.to_dict() for a in api.get_assignments()],
            "todo": [t.to_dict() for t in api.get_todo()],
            "syllabi": {},  # populated lazily on tool call
            "calendar_events": [],
        }
    except Exception:
        print(f"WARN: no snapshot at {snapshot_path} and live Canvas fetch failed", file=sys.stderr)
        return {"courses": [], "assignments": [], "todo": [], "syllabi": {}, "calendar_events": []}


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--contributor", required=True, help="Contributor ID (used as anonymization salt; e.g. 'alice')")
    p.add_argument("--queries", help="File of queries, one per line. Default: built-in CANONICAL_QUERIES.")
    p.add_argument("--output", required=True, help="Output JSONL path.")
    p.add_argument("--endpoint", default=os.environ.get("TEACHER_ENDPOINT", "http://localhost:18080/v1"))
    p.add_argument("--model", default=os.environ.get("TEACHER_MODEL", "nvidia/Gemma-4-31B-IT-NVFP4"))
    p.add_argument("--max-trajectories", type=int, default=20)
    p.add_argument("--anonymize", default=True, action="store_true")
    args = p.parse_args()

    full = _import_tools()
    print(f"[tools] {'full canvas_tui registry' if full else 'minimal standalone schemas'} ({len(TOOL_SCHEMAS)} tools)")

    if args.queries:
        queries = [q.strip() for q in Path(args.queries).read_text().splitlines() if q.strip() and not q.startswith("#")]
    else:
        queries = list(CANONICAL_QUERIES)
    queries = queries[: args.max_trajectories]
    print(f"[queries] running {len(queries)} canonical queries")

    snapshot = load_snapshot(args.contributor)
    print(f"[snapshot] {sum(len(v) if isinstance(v, list) else 1 for v in snapshot.values())} items across {list(snapshot.keys())}")

    out = []
    for i, q in enumerate(queries):
        print(f"\n[{i+1}/{len(queries)}] {q[:80]}")
        try:
            rec = collect_one(q, snapshot, args.contributor, args.endpoint, args.model)
            if args.anonymize:
                rec = anonymize_record(rec, args.contributor)
            out.append(rec)
            print(f"  {len(rec['trajectory'])} trajectory steps")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("\n".join(json.dumps(r) for r in out) + "\n")
    print(f"\n[wrote] {args.output} ({len(out)} trajectories)")


if __name__ == "__main__":
    main()
