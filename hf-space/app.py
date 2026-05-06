"""Canvas Calendar Agent — HF Space (ChatInterface + ZeroGPU + agent loop with mock tools)."""

from __future__ import annotations

import json
import re

import gradio as gr
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    import spaces
    GPU_DECORATOR = spaces.GPU(duration=60)
except Exception:
    def _noop(fn): return fn
    GPU_DECORATOR = _noop

MODEL_ID = "kleinpanic93/canvas-calendar-agent-v7-dpo"
MAX_TURNS = 2  # was 4 — model over-chained tool calls across rounds
MAX_NEW_TOKENS = 384

_TOOL_CALL_RE = re.compile(r"<\|tool_call>(.*?)<tool_call\|>", re.DOTALL)
_FUNC_RE = re.compile(r"^call:([\w.]+)\{(.*)\}$", re.DOTALL)


def _args_to_dict(args_str: str) -> dict:
    strings: list[str] = []

    def _stash(m):
        strings.append(m.group(1))
        return f'"__S{len(strings) - 1}__"'

    sanitized = re.sub(r'<\|"\|>([^<]*(?:<(?!\|"\|>)[^<]*)*)<\|"\|>', _stash, args_str, flags=re.DOTALL)
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
    out = []
    for match in _TOOL_CALL_RE.finditer(text):
        body = match.group(1).strip()
        m = _FUNC_RE.match(body)
        if not m:
            continue
        try:
            args = _args_to_dict(m.group(2))
        except Exception:
            continue
        out.append({"tool": m.group(1), "args": args})
    return out


def format_tool_result(tool_name: str, result: dict) -> str:
    body = json.dumps(result)
    return f'<|tool_response>response:{tool_name}{{value:<|"|>{body}<|"|>}}<tool_response|>'


def extract_final_answer(text: str) -> str:
    # Strip both tool-call and stray tool-response markers the model sometimes hallucinates.
    cleaned = re.sub(r"<\|tool_call>.*?<tool_call\|>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<\|tool_response>.*?<tool_response\|>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<\|tool_response>", "", cleaned)
    cleaned = re.sub(r"<turn\|>|<\|turn>", "", cleaned)
    return cleaned.strip()


def summarize_tool_results(tool_log: list[dict]) -> str:
    """Fallback final answer when the model only emitted tool calls without composing prose."""
    if not tool_log:
        return "(no final answer)"
    parts = []
    for t in tool_log:
        result = t.get("result", {})
        items = result.get("items") if isinstance(result, dict) else None
        if isinstance(items, list) and items:
            parts.append(f"{t['tool']} returned {len(items)} item(s)")
        elif isinstance(result, dict) and "blocks" in result:
            parts.append(f"{t['tool']} found {len(result.get('blocks', []))} free block(s)")
        else:
            parts.append(f"{t['tool']} ran successfully")
    return "Done. " + "; ".join(parts) + "."


SYSTEM_PROMPT = """You are the Canvas Calendar Agent. You have these 18 tools available:
- canvas.{get_assignments,get_course,get_grades,get_syllabus,get_todo,list_announcements,list_courses,list_planner_items}
- calendar.{create_event,delete_event,find_free_blocks,list_events,modify_event}
- reranker.priority_hint
- study.{exam_bracket,recommend_block_size,semester_schedule,spaced_schedule}

RULES (follow strictly):
1. Call the MINIMUM number of tools needed — usually ONE — to directly answer the user's question.
2. Don't call tools speculatively. Don't fetch data the user didn't ask for.
3. Don't iterate over courses/items unless the user explicitly asked for per-item detail.
4. After tool results come back, IMMEDIATELY produce a concise final answer. Do NOT call more tools.

Tool-call format: `<|tool_call>call:tool.name{arg:value}<tool_call|>`"""


_MOCK_ASSIGNMENTS = [
    {"id": 101, "title": "CS3704 PM4 Submission", "course": "CS 3704", "due_at": "2026-05-08T23:59:00Z", "points": 100},
    {"id": 102, "title": "ECE3574 Final Project", "course": "ECE 3574", "due_at": "2026-05-10T17:00:00Z", "points": 200},
    {"id": 103, "title": "MATH2114 Final Exam", "course": "MATH 2114", "due_at": "2026-05-12T08:00:00Z", "points": 300},
    {"id": 104, "title": "PHYS2306 HW7", "course": "PHYS 2306", "due_at": "2026-05-06T23:59:00Z", "points": 50},
]
_MOCK_COURSES = [
    {"id": 1, "name": "Software Engineering", "code": "CS 3704", "credits": 3},
    {"id": 2, "name": "Applied Software Design", "code": "ECE 3574", "credits": 3},
    {"id": 3, "name": "Linear Algebra", "code": "MATH 2114", "credits": 3},
    {"id": 4, "name": "Foundations of Physics II", "code": "PHYS 2306", "credits": 4},
]


def mock_tool_result(tool_name: str, args: dict) -> dict:
    if tool_name == "canvas.get_assignments":
        return {"items": _MOCK_ASSIGNMENTS}
    if tool_name == "canvas.get_course":
        cid = int(args.get("course_id", 1))
        return next((c for c in _MOCK_COURSES if c["id"] == cid), _MOCK_COURSES[0])
    if tool_name == "canvas.get_grades":
        return {"items": [{"course": c["code"], "grade": "A-", "score": 91.2} for c in _MOCK_COURSES]}
    if tool_name == "canvas.get_syllabus":
        return {"course_id": args.get("course_id", 1), "syllabus": "MWF 10–10:50 McBryde 113. Final TBD."}
    if tool_name == "canvas.get_todo":
        return {"items": [{"title": "Submit PM4", "course": "CS 3704", "due": "2026-05-08T23:59:00Z"}]}
    if tool_name == "canvas.list_announcements":
        return {"items": [{"course": "CS 3704", "title": "PM4 rubric posted"}, {"course": "MATH 2114", "title": "Final: McBryde 100"}]}
    if tool_name == "canvas.list_courses":
        return {"items": _MOCK_COURSES}
    if tool_name == "canvas.list_planner_items":
        return {"items": [{"title": a["title"], "course": a["course"], "due": a["due_at"]} for a in _MOCK_ASSIGNMENTS]}
    if tool_name == "calendar.create_event":
        return {"event_id": "evt_001", "created": True, "title": args.get("title")}
    if tool_name == "calendar.delete_event":
        return {"event_id": args.get("event_id"), "deleted": True}
    if tool_name == "calendar.find_free_blocks":
        return {"blocks": [
            {"start": "2026-05-06T09:00:00", "end": "2026-05-06T11:30:00", "duration_min": 150},
            {"start": "2026-05-07T13:00:00", "end": "2026-05-07T17:00:00", "duration_min": 240},
        ]}
    if tool_name == "calendar.list_events":
        return {"events": [{"id": "evt_001", "title": "CS 3704 lecture", "start": "2026-05-06T10:00:00"}]}
    if tool_name == "calendar.modify_event":
        return {"event_id": args.get("event_id"), "modified": True}
    if tool_name == "reranker.priority_hint":
        return {"ranked": _MOCK_ASSIGNMENTS, "rationale": "sorted by due date"}
    if tool_name == "study.exam_bracket":
        return {"bracket": [{"phase": "deep_prep", "blocks_min": 240}, {"phase": "review", "blocks_min": 150}, {"phase": "light_cram", "blocks_min": 90}]}
    if tool_name == "study.recommend_block_size":
        return {"recommended_block_min": 90}
    if tool_name == "study.semester_schedule":
        return {"weeks": [{"week": 1, "study_hours": 9}, {"week": 14, "study_hours": 22}]}
    if tool_name == "study.spaced_schedule":
        return {"intervals_days_before_exam": [9, 4, 1]}
    return {"ok": True, "note": f"mock {tool_name}", "args": args}


print(f"Loading {MODEL_ID} ...", flush=True)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.bfloat16)
model.requires_grad_(False)
print("Model ready.", flush=True)


def _to_input_ids(messages):
    encoded = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True,
    )
    return encoded["input_ids"]


@GPU_DECORATOR
def generate_step(messages):
    input_ids = _to_input_ids(messages)
    if torch.cuda.is_available():
        model.to("cuda")
        input_ids = input_ids.to("cuda")
    with torch.inference_mode():
        out = model.generate(
            input_ids,
            do_sample=False,
            max_new_tokens=MAX_NEW_TOKENS,
            pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(out[0, input_ids.shape[1]:], skip_special_tokens=False)


def chat(message, history):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history or []:
        if isinstance(h, dict):
            msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        elif isinstance(h, (list, tuple)) and len(h) >= 2:
            if h[0]: msgs.append({"role": "user", "content": h[0]})
            if h[1]: msgs.append({"role": "assistant", "content": h[1]})
    msgs.append({"role": "user", "content": message})

    tool_log = []
    raw = ""
    MAX_CALLS_PER_TURN = 2  # cap concurrent tool calls in a single generation
    for _ in range(MAX_TURNS):
        raw = generate_step(msgs)
        calls = parse_tool_calls(raw)[:MAX_CALLS_PER_TURN]
        msgs.append({"role": "assistant", "content": raw})
        if not calls:
            break
        for call in calls:
            # Skip duplicate (same tool+args already called this conversation)
            already = any(
                t["tool"] == call["tool"] and t["args"] == call["args"]
                for t in tool_log
            )
            if already:
                continue
            result = mock_tool_result(call["tool"], call["args"])
            tool_log.append({"tool": call["tool"], "args": call["args"], "result": result})
            msgs.append({"role": "user", "content": format_tool_result(call["tool"], result)})

    final = extract_final_answer(raw)
    if not final or final == "(no final answer)":
        final = summarize_tool_results(tool_log)
    if tool_log:
        tool_md = "\n".join(
            f"- `{t['tool']}({json.dumps(t['args'])})` -> `{json.dumps(t['result'])[:120]}...`"
            for t in tool_log
        )
        return f"{final}\n\n---\n**Tool calls (mock data — Space has no Canvas creds):**\n{tool_md}"
    return final


THEME = gr.themes.Soft(
    primary_hue="red",
    secondary_hue="slate",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
).set(
    body_background_fill="#0a0a0b",
    body_background_fill_dark="#0a0a0b",
    block_background_fill="#15151a",
    block_background_fill_dark="#15151a",
    block_border_color="#27272f",
    block_border_color_dark="#27272f",
    body_text_color="#e5e7eb",
    body_text_color_dark="#e5e7eb",
    button_primary_background_fill="#d63e36",
    button_primary_background_fill_dark="#d63e36",
    button_primary_background_fill_hover="#b83830",
    button_primary_background_fill_hover_dark="#b83830",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
)

DESCRIPTION_MD = """
**Canvas LMS calendar + study-planning agent.** Fine-tuned Gemma-4-E2B-IT with DPO on a custom preference dataset (1,071 pairs, 90.3% reward accuracy, 0.22 train loss).

The model speaks the **native Gemma-4 tool-call protocol** for 18 tools — `canvas.*` (8 tools for assignments / courses / grades / syllabi / planner), `calendar.*` (5 for scheduling / free-block search), `reranker.*` (priority hints), and `study.*` (4 for exam prep, spaced repetition, semester planning).

**Tool results are mocked** — this Space has no Canvas credentials. Install the SDK locally with your own Canvas token for real data: `pip install canvas-sdk[autodownload]`.

[Model](https://huggingface.co/kleinpanic93/canvas-calendar-agent-v7-dpo) · [Dataset](https://huggingface.co/datasets/kleinpanic93/canvas-calendar-preferences-v7) · [Collection (9-method matrix)](https://huggingface.co/collections/kleinpanic93/canvas-calendar-agent-v30-69fa6462f697e0342b21dfe0) · [GitHub](https://github.com/kleinpanic/CS3704-Canvas-Project)

> First request after a quiet period takes ~30 s while ZeroGPU cold-starts. Subsequent requests are fast.
"""

demo = gr.ChatInterface(
    fn=chat,
    title="🎓 Canvas Calendar Agent",
    description=DESCRIPTION_MD,
    examples=[
        "What assignments do I have due this week?",
        "Find me a 2-hour free block tomorrow afternoon",
        "Build me an exam-prep bracket for the May 12 final",
        "Rank my todos by priority",
        "What's on my calendar this week?",
        "Plan a spaced-repetition schedule for my Linear Algebra final",
    ],
    type="messages",
    theme=THEME,
    cache_examples=False,
)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
