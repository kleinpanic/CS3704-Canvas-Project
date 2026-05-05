"""Canvas Calendar Agent — HuggingFace Space inference backend.

Loads kleinpanic93/canvas-calendar-agent-v7-dpo (Gemma4 + DPO) and exposes a
Gradio chat UI. Tool calls are executed against MOCK Canvas data because the
Space has no Canvas credentials; the model still emits the native Gemma4
tool-call protocol so users can see exactly which tools the agent invokes.
"""

from __future__ import annotations

import json
import re
from typing import Any

import gradio as gr
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "kleinpanic93/canvas-calendar-agent-v7-dpo"
MAX_TURNS = 4
MAX_NEW_TOKENS = 512

_TOOL_CALL_RE = re.compile(r"<\|tool_call>(.*?)<tool_call\|>", re.DOTALL)
_FUNC_RE = re.compile(r"^call:([\w.]+)\{(.*)\}$", re.DOTALL)


def _args_to_dict(args_str: str) -> dict:
    strings: list[str] = []

    def _stash(m: re.Match) -> str:
        strings.append(m.group(1))
        return f'"__S{len(strings) - 1}__"'

    sanitized = re.sub(
        r"<\|\"\|>([^<]*(?:<(?!\|\"\|>)[^<]*)*)<\|\"\|>",
        _stash,
        args_str,
        flags=re.DOTALL,
    )
    sanitized = re.sub(r"(?:^|(?<=,)|(?<=\{))(\s*\w+):", r'"\1":', sanitized)
    obj = json.loads("{" + sanitized + "}")

    def _restore(v):
        if isinstance(v, str):
            m = re.fullmatch(r"__S(\d+)__", v)
            return strings[int(m.group(1))] if m else v
        if isinstance(v, dict):
            return {k: _restore(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_restore(x) for x in v]
        return v

    return _restore(obj)


def parse_tool_calls(text: str) -> list[dict]:
    results = []
    for match in _TOOL_CALL_RE.finditer(text):
        body = match.group(1).strip()
        m = _FUNC_RE.match(body)
        if not m:
            continue
        try:
            arguments = _args_to_dict(m.group(2))
        except (json.JSONDecodeError, IndexError, KeyError):
            continue
        results.append({"tool": m.group(1), "args": arguments})
    return results


def format_tool_result(tool_name: str, result: dict) -> str:
    body = json.dumps(result)
    return f'<|tool_response>response:{tool_name}{{value:<|"|>{body}<|"|>}}<tool_response|>'


def extract_final_answer(text: str) -> str:
    return re.sub(r"<\|tool_call>.*?<tool_call\|>", "", text, flags=re.DOTALL).strip()


# 18-tool catalog — canonical names matching canvas_sdk.agent_tools.REGISTRY.
# Mock data here lets the HF Space exercise the full tool surface without
# needing real Canvas credentials.
TOOL_CATALOG = {
    "canvas.get_assignments": {
        "description": "List upcoming Canvas assignments across enrolled courses.",
        "args": {"horizon_days": "int (default 7)"},
    },
    "canvas.get_course": {
        "description": "Get metadata for a specific course (name, code, term).",
        "args": {"course_id": "int"},
    },
    "canvas.get_grades": {
        "description": "Get current grades for one or all courses.",
        "args": {"course_id": "int (optional)"},
    },
    "canvas.get_syllabus": {
        "description": "Fetch the course syllabus body.",
        "args": {"course_id": "int"},
    },
    "canvas.get_todo": {
        "description": "Get the user's Canvas to-do list.",
        "args": {},
    },
    "canvas.list_announcements": {
        "description": "List recent course announcements.",
        "args": {"course_id": "int (optional)"},
    },
    "canvas.list_courses": {
        "description": "List enrolled courses for the current term.",
        "args": {"term": "str (optional)"},
    },
    "canvas.list_planner_items": {
        "description": "List items from the Canvas planner.",
        "args": {"start_date": "ISO 8601", "end_date": "ISO 8601"},
    },
    "calendar.create_event": {
        "description": "Create a new calendar event.",
        "args": {"title": "str", "start": "ISO 8601", "end": "ISO 8601"},
    },
    "calendar.delete_event": {
        "description": "Delete a calendar event.",
        "args": {"event_id": "str"},
    },
    "calendar.find_free_blocks": {
        "description": "Find contiguous free blocks of time.",
        "args": {"min_minutes": "int", "horizon_days": "int"},
    },
    "calendar.list_events": {
        "description": "List events from the user's local calendar.",
        "args": {"start_iso": "ISO 8601", "end_iso": "ISO 8601"},
    },
    "calendar.modify_event": {
        "description": "Modify an existing calendar event.",
        "args": {"event_id": "str", "patch": "dict"},
    },
    "reranker.priority_hint": {
        "description": "Score and rank a list of items by urgency/priority.",
        "args": {"items": "list", "query": "str"},
    },
    "study.exam_bracket": {
        "description": "Build an exam-prep bracket: deep prep, review, light cram blocks before exam_date.",
        "args": {"exam_date": "ISO 8601", "topics": "list"},
    },
    "study.recommend_block_size": {
        "description": "Recommend study-block size based on credit hours and topic difficulty.",
        "args": {"credit_hours": "int", "difficulty": "str"},
    },
    "study.semester_schedule": {
        "description": "Generate a semester study schedule from courses and exam dates.",
        "args": {"courses": "list", "exam_dates": "list"},
    },
    "study.spaced_schedule": {
        "description": "Compute Cepeda-spaced repetition intervals for an exam.",
        "args": {"exam_date": "ISO 8601", "sessions": "int"},
    },
}


def build_system_prompt() -> str:
    catalog_lines = ["Available tools:"]
    for name, spec in TOOL_CATALOG.items():
        catalog_lines.append(f"- {name}: {spec['description']}")
        if spec["args"]:
            args_str = ", ".join(f"{k}={v}" for k, v in spec["args"].items())
            catalog_lines.append(f"    args: {args_str}")
    catalog = "\n".join(catalog_lines)
    return (
        "You are a Canvas LMS calendar and study planning assistant. "
        "You have access to tools that query the user's Canvas account, "
        "their local calendar, and study-planning utilities. "
        "Emit tool calls in the format:\n"
        "<|tool_call>call:tool.name{arg:value,arg2:value2}<tool_call|>\n"
        "After receiving tool results, produce a concise final answer.\n\n"
        f"{catalog}"
    )


_MOCK_ASSIGNMENTS = [
    {"id": 101, "title": "CS3704 PM4 Submission", "course": "CS 3704", "due_at": "2026-05-08T23:59:00Z", "points": 100, "submitted": False},
    {"id": 102, "title": "ECE3574 Final Project Report", "course": "ECE 3574", "due_at": "2026-05-10T17:00:00Z", "points": 200, "submitted": False},
    {"id": 103, "title": "MATH2114 Final Exam", "course": "MATH 2114", "due_at": "2026-05-12T08:00:00Z", "points": 300, "submitted": False},
    {"id": 104, "title": "PHYS2306 HW7", "course": "PHYS 2306", "due_at": "2026-05-06T23:59:00Z", "points": 50, "submitted": True},
]
_MOCK_COURSES = [
    {"id": 1, "name": "Software Engineering", "code": "CS 3704", "term": "Spring 2026", "credits": 3},
    {"id": 2, "name": "Applied Software Design", "code": "ECE 3574", "term": "Spring 2026", "credits": 3},
    {"id": 3, "name": "Linear Algebra", "code": "MATH 2114", "term": "Spring 2026", "credits": 3},
    {"id": 4, "name": "Foundations of Physics II", "code": "PHYS 2306", "term": "Spring 2026", "credits": 4},
]
_MOCK_ANNOUNCEMENTS = [
    {"course": "CS 3704", "title": "PM4 grading rubric posted", "posted_at": "2026-05-04T14:00:00Z", "body": "See Canvas for the updated rubric. Points distribution unchanged."},
    {"course": "MATH 2114", "title": "Final exam location: McBryde 100", "posted_at": "2026-05-03T09:00:00Z", "body": "Bring your VT ID."},
]


def mock_tool_result(tool_name: str, args: dict) -> dict:
    """Return realistic placeholder data for any of the 18 SDK tools — Space has no Canvas creds."""
    if tool_name == "canvas.get_assignments":
        horizon = int(args.get("horizon_days", 7))
        return {"horizon_days": horizon, "items": _MOCK_ASSIGNMENTS}
    if tool_name == "canvas.get_course":
        cid = int(args.get("course_id", 1))
        match = next((c for c in _MOCK_COURSES if c["id"] == cid), _MOCK_COURSES[0])
        return match
    if tool_name == "canvas.get_grades":
        return {"items": [{"course": c["code"], "grade": "A-", "score": 91.2} for c in _MOCK_COURSES]}
    if tool_name == "canvas.get_syllabus":
        return {"course_id": args.get("course_id", 1), "syllabus": "Course meets MWF 10–10:50 in McBryde 113. Final exam: TBD. Prof: @PROF1. Email: @PROF_EMAIL."}
    if tool_name == "canvas.get_todo":
        return {"items": [
            {"title": "Watch lecture 14", "course": "CS 3704", "kind": "video"},
            {"title": "Submit PM4", "course": "CS 3704", "kind": "assignment", "due": "2026-05-08T23:59:00Z"},
        ]}
    if tool_name == "canvas.list_announcements":
        return {"items": _MOCK_ANNOUNCEMENTS}
    if tool_name == "canvas.list_courses":
        return {"items": _MOCK_COURSES}
    if tool_name == "canvas.list_planner_items":
        return {"items": [
            {"title": a["title"], "course": a["course"], "due": a["due_at"], "kind": "assignment"}
            for a in _MOCK_ASSIGNMENTS
        ]}
    if tool_name == "calendar.create_event":
        return {"event_id": "evt_mock_001", "created": True, "title": args.get("title"), "start": args.get("start")}
    if tool_name == "calendar.delete_event":
        return {"event_id": args.get("event_id"), "deleted": True}
    if tool_name == "calendar.find_free_blocks":
        return {"blocks": [
            {"start": "2026-05-06T09:00:00", "end": "2026-05-06T11:30:00", "duration_min": 150},
            {"start": "2026-05-06T14:00:00", "end": "2026-05-06T16:00:00", "duration_min": 120},
            {"start": "2026-05-07T13:00:00", "end": "2026-05-07T17:00:00", "duration_min": 240},
            {"start": "2026-05-08T09:00:00", "end": "2026-05-08T11:00:00", "duration_min": 120},
        ]}
    if tool_name == "calendar.list_events":
        return {"events": [
            {"id": "evt_001", "title": "CS 3704 lecture", "start": "2026-05-06T10:00:00", "end": "2026-05-06T10:50:00"},
            {"id": "evt_002", "title": "Office hours - ECE 3574", "start": "2026-05-07T15:00:00", "end": "2026-05-07T16:00:00"},
        ]}
    if tool_name == "calendar.modify_event":
        return {"event_id": args.get("event_id"), "modified": True, "patch_applied": args.get("patch", {})}
    if tool_name == "reranker.priority_hint":
        items = args.get("items", _MOCK_ASSIGNMENTS)
        ranked = sorted(items, key=lambda x: x.get("due_at", x.get("due", "")), reverse=False) if items else []
        return {"ranked": ranked, "rationale": "sorted by earliest due date with weight on point value"}
    if tool_name == "study.exam_bracket":
        return {"bracket": [
            {"phase": "deep_prep", "start": "2026-05-08", "end": "2026-05-09", "blocks_min": 240},
            {"phase": "review", "start": "2026-05-10", "end": "2026-05-11", "blocks_min": 150},
            {"phase": "light_cram", "start": "2026-05-12T06:00:00", "end": "2026-05-12T07:30:00", "blocks_min": 90},
        ]}
    if tool_name == "study.recommend_block_size":
        ch = int(args.get("credit_hours", 3))
        diff = args.get("difficulty", "medium")
        size = {"easy": 60, "medium": 90, "hard": 120}.get(diff, 90)
        return {"credit_hours": ch, "difficulty": diff, "recommended_block_min": size}
    if tool_name == "study.semester_schedule":
        return {"weeks": [
            {"week": 1, "focus": "syllabus review + foundations", "study_hours": 9},
            {"week": 2, "focus": "PM1 + HW1", "study_hours": 12},
            {"week": "...", "focus": "...", "study_hours": "..."},
            {"week": 14, "focus": "finals prep", "study_hours": 22},
        ]}
    if tool_name == "study.spaced_schedule":
        # Cepeda spacing: +1d, +4d, +9d before exam (12-day window)
        return {"intervals_days_before_exam": [9, 4, 1], "n_sessions": int(args.get("sessions", 3))}
    return {"ok": True, "note": f"unhandled tool {tool_name}", "args": args}


print(f"Loading {MODEL_ID} ...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
print("Model ready.")


def generate_once(messages: list[dict]) -> str:
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(model.device)
    with torch.inference_mode():
        out = model.generate(
            inputs,
            do_sample=False,
            max_new_tokens=MAX_NEW_TOKENS,
            pad_token_id=tokenizer.eos_token_id,
        )
    new_tokens = out[0, inputs.shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=False)


def predict(user_msg: str) -> tuple[str, list[dict], list[dict]]:
    """Run the agent loop and return (final_answer, transcript, tool_calls)."""
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user_msg},
    ]
    transcript: list[dict] = list(messages)
    all_tool_calls: list[dict] = []

    raw = ""
    for _turn in range(MAX_TURNS):
        raw = generate_once(messages)
        calls = parse_tool_calls(raw)
        messages.append({"role": "assistant", "content": raw})
        transcript.append({"role": "assistant", "content": raw})

        if not calls:
            return extract_final_answer(raw), transcript, all_tool_calls

        all_tool_calls.extend(calls)
        for call in calls:
            result = mock_tool_result(call["tool"], call["args"])
            tool_msg = format_tool_result(call["tool"], result)
            messages.append({"role": "user", "content": tool_msg})
            transcript.append(
                {"role": "tool", "content": tool_msg, "tool": call["tool"], "args": call["args"], "result": result}
            )

    final = extract_final_answer(raw) or "(max turns reached)"
    return final, transcript, all_tool_calls


def chat(user_msg: str, history: list[Any]) -> tuple[str, list[Any], dict]:
    answer, transcript, tool_calls = predict(user_msg)
    history = history + [(user_msg, answer)]
    debug = {"transcript": transcript, "tool_calls": tool_calls}
    return "", history, debug


with gr.Blocks(title="Canvas Calendar Agent Demo") as demo:
    gr.Markdown(
        "# Canvas Calendar Agent — Live Demo\n\n"
        f"Model: **{MODEL_ID}** (Gemma-4-E2B-IT + DPO).\n\n"
        "Tool calls execute against **mock Canvas data** — this Space has no "
        "credentials. For the real thing, install the SDK locally with your "
        "own Canvas token. The model still speaks the native Gemma4 tool-call "
        "format so you can see exactly which tools it tries to invoke."
    )
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(label="Conversation", height=420)
            msg = gr.Textbox(
                label="Your message",
                placeholder="e.g. What's due this week? · Plan my finals study schedule",
                lines=2,
            )
            with gr.Row():
                send = gr.Button("Send", variant="primary")
                clear = gr.Button("Clear")
        with gr.Column(scale=1):
            debug_view = gr.JSON(label="Transcript + tool calls")

    send.click(chat, inputs=[msg, chatbot], outputs=[msg, chatbot, debug_view])
    msg.submit(chat, inputs=[msg, chatbot], outputs=[msg, chatbot, debug_view])
    clear.click(lambda: ([], {}), outputs=[chatbot, debug_view])


if __name__ == "__main__":
    demo.queue().launch()
