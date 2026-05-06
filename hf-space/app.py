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
        # Gemma-4 official sampling for production inference per
        # https://ai.google.dev/gemma/docs/core/model_card_4
        out = model.generate(
            input_ids,
            do_sample=True,
            temperature=1.0,
            top_p=0.95,
            top_k=64,
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
        rows = "\n".join(
            f"| `{t['tool']}` | `{json.dumps(t['args'])[:70]}` | `{json.dumps(t['result'])[:90]}` |"
            for t in tool_log
        )
        table = f"| Tool | Args | Result |\n|------|------|--------|\n{rows}"
        label = f"{len(tool_log)} tool call{'s' if len(tool_log) > 1 else ''}"
        return f"{final}\n\n<details><summary>🔧 {label} (mock data)</summary>\n\n{table}\n\n</details>"
    return final


THEME = gr.themes.Monochrome(
    primary_hue="red",
    secondary_hue="neutral",
    neutral_hue="neutral",
    font=["Segoe UI", "system-ui", gr.themes.GoogleFont("Inter"), "sans-serif"],
    font_mono=["Cascadia Code", "Consolas", "ui-monospace", "monospace"],
).set(
    body_background_fill="#0a0a0b",
    body_background_fill_dark="#0a0a0b",
    block_background_fill="#111114",
    block_background_fill_dark="#111114",
    block_border_color="#2e2e38",
    block_border_color_dark="#2e2e38",
    block_border_width="1px",
    block_radius="6px",
    body_text_color="#d4d4db",
    body_text_color_dark="#d4d4db",
    button_primary_background_fill="#d63e36",
    button_primary_background_fill_dark="#d63e36",
    button_primary_background_fill_hover="#b83830",
    button_primary_background_fill_hover_dark="#b83830",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
    button_secondary_background_fill="#1a1a1f",
    button_secondary_background_fill_dark="#1a1a1f",
    button_secondary_border_color="#2e2e38",
    button_secondary_border_color_dark="#2e2e38",
    input_background_fill="#111114",
    input_background_fill_dark="#111114",
    input_border_color="#2e2e38",
    input_border_color_dark="#2e2e38",
    chatbot_text_size="sm",
)

CUSTOM_CSS = """
.gradio-container { max-width: 960px !important; padding: 24px 20px !important; }
.block { box-shadow: none !important; border-radius: 8px !important; }
/* chatbot */
#component-0 .chatbot { min-height: 440px; }
.message-bubble-border { border-radius: 8px !important; }
.user .message {
    background: #d63e36 !important;
    color: #fff !important;
    border-radius: 8px 8px 2px 8px !important;
}
.bot .message {
    background: #18181f !important;
    border: 1px solid #2e2e38 !important;
    border-radius: 8px 8px 8px 2px !important;
    line-height: 1.6 !important;
}
/* bot message: tool-call table */
.bot .message table { font-size: 0.75rem !important; border-collapse: collapse !important; width: 100% !important; margin-top: 6px; }
.bot .message th, .bot .message td { padding: 3px 8px !important; border: 1px solid #2e2e38 !important; text-align: left !important; }
.bot .message th { background: #111114 !important; color: #9ca3af !important; font-weight: 500 !important; }
.bot .message details summary { cursor: pointer; color: #6b7280; font-size: 0.78rem; user-select: none; }
/* input */
.input-row textarea { border-radius: 6px !important; font-size: 0.875rem !important; min-height: 48px !important; }
/* example buttons — pill style */
.examples-holder { flex-wrap: wrap !important; gap: 6px !important; }
.examples-holder button {
    border-radius: 20px !important;
    font-size: 0.78rem !important;
    padding: 4px 14px !important;
    border: 1px solid #2e2e38 !important;
    background: #18181f !important;
    transition: border-color 0.15s, background 0.15s !important;
}
.examples-holder button:hover { border-color: #d63e36 !important; background: #1f1010 !important; }
/* description */
.description { font-size: 0.82rem !important; line-height: 1.6 !important; color: #9ca3af !important; }
"""

DESCRIPTION_MD = """
Fine-tuned **Gemma-4-E2B-IT** (DPO · β=0.1 · 181 trajectories · 90.3% reward accuracy) — speaks the native Gemma-4 tool protocol for **18 tools** across 4 families:

`canvas.*` assignments · grades · syllabi · planner &nbsp;|&nbsp; `calendar.*` scheduling · free blocks &nbsp;|&nbsp; `reranker.*` priority hints &nbsp;|&nbsp; `study.*` exam prep · spaced repetition

> ⚠️ **Mock data** — no Canvas credentials in this Space. For live data: `pip install canvas-sdk[autodownload]`
> ⏱ Cold-start after inactivity ~30 s (ZeroGPU). Subsequent responses are fast.

[Model](https://huggingface.co/kleinpanic93/canvas-calendar-agent-v7-dpo) · [Dataset](https://huggingface.co/datasets/kleinpanic93/canvas-calendar-preferences-v7) · [Collection](https://huggingface.co/collections/kleinpanic93/canvas-calendar-agent-v30-69fa6462f697e0342b21dfe0) · [GitHub](https://github.com/kleinpanic/CS3704-Canvas-Project) · [Docs](https://kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/method.html)
"""

demo = gr.ChatInterface(
    fn=chat,
    title="Canvas Calendar Agent",
    description=DESCRIPTION_MD,
    examples=[
        "What assignments do I have due this week?",
        "Find me a 2-hour free block tomorrow afternoon",
        "Build me an exam-prep bracket for the May 12 final",
        "Rank my todos by priority",
        "What are my current grades?",
        "Plan a spaced-repetition schedule for my Linear Algebra final",
        "Create a study block from 3pm to 5pm tomorrow",
        "What announcements are in my CS 3704 course?",
    ],
    type="messages",
    theme=THEME,
    css=CUSTOM_CSS,
    cache_examples=False,
    fill_height=True,
)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
