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


TOOL_CATALOG = {
    "canvas.get_assignments": {
        "description": "List upcoming Canvas assignments across enrolled courses.",
        "args": {"days_ahead": "int (default 14)"},
    },
    "canvas.get_todo": {
        "description": "Get the user's Canvas to-do list.",
        "args": {},
    },
    "canvas.get_announcements": {
        "description": "List recent course announcements.",
        "args": {"course_id": "int (optional)"},
    },
    "canvas.get_course_info": {
        "description": "Get metadata for a specific course (name, code, term).",
        "args": {"course_id": "int"},
    },
    "canvas.get_calendar_events": {
        "description": "List Canvas calendar events.",
        "args": {"start_date": "ISO 8601", "end_date": "ISO 8601"},
    },
    "canvas.list_planner_items": {
        "description": "List items from the Canvas planner.",
        "args": {"start_date": "ISO 8601", "end_date": "ISO 8601"},
    },
    "calendar.list_events": {
        "description": "List events from the user's local calendar.",
        "args": {"start_date": "ISO 8601", "end_date": "ISO 8601"},
    },
    "calendar.find_free_blocks": {
        "description": "Find contiguous free blocks of time.",
        "args": {"min_minutes": "int", "start": "ISO 8601", "end": "ISO 8601"},
    },
    "calendar.schedule_block": {
        "description": "Schedule a study block.",
        "args": {"title": "str", "start": "ISO 8601", "duration_min": "int"},
    },
    "calendar.create_event": {
        "description": "Create a new calendar event.",
        "args": {"title": "str", "start": "ISO 8601", "end": "ISO 8601"},
    },
    "calendar.update_event": {
        "description": "Update an existing calendar event.",
        "args": {"event_id": "str", "patch": "dict"},
    },
    "calendar.delete_event": {
        "description": "Delete a calendar event.",
        "args": {"event_id": "str"},
    },
    "study.compute_spacing_intervals": {
        "description": "Compute spaced-repetition intervals for an exam.",
        "args": {"exam_date": "ISO 8601", "n_sessions": "int"},
    },
    "study.estimate_total_prep_hours": {
        "description": "Estimate total prep hours for an assignment or exam.",
        "args": {"item": "dict"},
    },
    "study.score_load": {
        "description": "Score the cognitive load of a week's workload.",
        "args": {"items": "list"},
    },
    "reranker.rank_assignments": {
        "description": "Rank assignments by urgency/importance.",
        "args": {"items": "list", "query": "str"},
    },
    "reranker.rank_announcements": {
        "description": "Rank announcements by relevance.",
        "args": {"items": "list", "query": "str"},
    },
    "reranker.rank_courses": {
        "description": "Rank courses by relevance to a query.",
        "args": {"items": "list", "query": "str"},
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


def mock_tool_result(tool_name: str, args: dict) -> dict:
    """Return placeholder data for any tool — Space has no Canvas access."""
    if tool_name == "canvas.get_assignments":
        return {
            "items": [
                {
                    "title": "CS3704 PM4 Submission",
                    "course": "CS 3704",
                    "due_at": "2026-05-08T23:59:00Z",
                    "points": 100,
                },
                {
                    "title": "ECE3574 Final Project Report",
                    "course": "ECE 3574",
                    "due_at": "2026-05-10T17:00:00Z",
                    "points": 200,
                },
                {
                    "title": "MATH2114 Final Exam",
                    "course": "MATH 2114",
                    "due_at": "2026-05-12T08:00:00Z",
                    "points": 300,
                },
            ]
        }
    if tool_name == "canvas.get_todo":
        return {"items": [{"title": "Watch lecture 14", "course": "CS 3704"}]}
    if tool_name == "canvas.get_announcements":
        return {
            "items": [
                {
                    "course": "CS 3704",
                    "title": "PM4 grading rubric posted",
                    "posted_at": "2026-05-04T14:00:00Z",
                }
            ]
        }
    if tool_name == "calendar.find_free_blocks":
        return {
            "blocks": [
                {"start": "2026-05-06T09:00:00", "end": "2026-05-06T11:30:00"},
                {"start": "2026-05-07T14:00:00", "end": "2026-05-07T17:00:00"},
            ]
        }
    if tool_name == "study.compute_spacing_intervals":
        return {"intervals_days": [10, 5, 2, 1]}
    if tool_name in {"reranker.rank_assignments", "reranker.rank_courses", "reranker.rank_announcements"}:
        return {"ranked": args.get("items", [])}
    return {"ok": True, "note": f"mock result for {tool_name}"}


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
