"""Canvas Calendar Agent — HF Space (Blocks layout, calendar pane, session state, 18-tool surface)."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

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
MAX_TURNS = 2
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


def format_tool_result(tool_name: str, result: Any) -> str:
    body = json.dumps(result)
    return f'<|tool_response>response:{tool_name}{{value:<|"|>{body}<|"|>}}<tool_response|>'


def extract_final_answer(text: str) -> str:
    cleaned = re.sub(r"<\|tool_call>.*?<tool_call\|>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<\|tool_response>.*?<tool_response\|>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<\|tool_response>", "", cleaned)
    cleaned = re.sub(r"<turn\|>|<\|turn>", "", cleaned)
    return cleaned.strip()


def summarize_tool_results(tool_log: list[dict]) -> str:
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
        elif isinstance(result, list):
            parts.append(f"{t['tool']} returned {len(result)} item(s)")
        else:
            parts.append(f"{t['tool']} ran successfully")
    return "Done. " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# InMemoryCalendarBackend — duplicated from canvas_sdk.backends.calendar_adapter.
# The HF Space deploy workflow only uploads hf-space/, so canvas_sdk is not
# importable here. The contract is kept identical to the SDK class so behaviour
# stays in lockstep with src/sdk/canvas_sdk/backends/calendar_adapter.py.
# ---------------------------------------------------------------------------

class InMemoryCalendarBackend:
    def __init__(self, seed_events: list[dict] | None = None) -> None:
        self._events: dict[str, dict[str, Any]] = {}
        self._counter = 100
        for ev in seed_events or []:
            eid = ev.get("id") or self._next_id()
            ev = {**ev, "id": eid}
            self._events[eid] = ev

    def _next_id(self) -> str:
        eid = f"evt_{self._counter:03d}"
        self._counter += 1
        return eid

    def _in_window(self, ev, start, end):
        if not (start or end):
            return True
        s = ev.get("start_iso")
        if not s:
            return True
        try:
            ev_start = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except ValueError:
            return True
        if ev_start.tzinfo is None:
            ev_start = ev_start.replace(tzinfo=dt.timezone.utc)
        if start and ev_start < start:
            return False
        if end and ev_start > end:
            return False
        return True

    def list_events(self, calendar_id="primary", start_iso=None, end_iso=None, include_all_day=True):
        start = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00")) if start_iso else None
        end = dt.datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else None
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=dt.timezone.utc)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=dt.timezone.utc)
        out = []
        for ev in self._events.values():
            if not include_all_day and ev.get("all_day"):
                continue
            if not self._in_window(ev, start, end):
                continue
            out.append(dict(ev))
        out.sort(key=lambda e: e.get("start_iso", ""))
        return out

    def find_free_blocks(self, min_minutes=90, horizon_days=7, earliest_hour=7, latest_hour=22, calendar_id="primary", exclude_weekends=False):
        now = dt.datetime.now(dt.timezone.utc)
        end = now + dt.timedelta(days=horizon_days)
        events = self.list_events(start_iso=now.isoformat(), end_iso=end.isoformat(), include_all_day=False)
        busy = []
        for ev in events:
            if ev.get("start_iso") and ev.get("end_iso"):
                s = dt.datetime.fromisoformat(str(ev["start_iso"]).replace("Z", "+00:00"))
                e = dt.datetime.fromisoformat(str(ev["end_iso"]).replace("Z", "+00:00"))
                if s.tzinfo is None: s = s.replace(tzinfo=dt.timezone.utc)
                if e.tzinfo is None: e = e.replace(tzinfo=dt.timezone.utc)
                busy.append((s, e))
        busy.sort()
        free_blocks = []
        cursor = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
        while cursor < end and len(free_blocks) < 20:
            if exclude_weekends and cursor.weekday() >= 5:
                cursor = (cursor + dt.timedelta(days=1)).replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
                continue
            day_start = cursor.replace(hour=max(cursor.hour, earliest_hour), minute=0, second=0, microsecond=0)
            day_end = cursor.replace(hour=latest_hour, minute=0, second=0, microsecond=0)
            slot_start = day_start
            if slot_start >= day_end:
                cursor = (cursor + dt.timedelta(days=1)).replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
                continue
            for b_s, b_e in busy:
                if b_s >= day_end: break
                if b_e <= slot_start: continue
                if slot_start < b_s:
                    gap = int((b_s - slot_start).total_seconds() / 60)
                    if gap >= min_minutes:
                        free_blocks.append({
                            "start_iso": slot_start.isoformat(),
                            "end_iso": (slot_start + dt.timedelta(minutes=min_minutes)).isoformat(),
                            "minutes": min_minutes,
                        })
                slot_start = max(slot_start, b_e)
            gap = int((day_end - slot_start).total_seconds() / 60)
            if gap >= min_minutes:
                free_blocks.append({
                    "start_iso": slot_start.isoformat(),
                    "end_iso": (slot_start + dt.timedelta(minutes=min_minutes)).isoformat(),
                    "minutes": min_minutes,
                })
            cursor = (cursor + dt.timedelta(days=1)).replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
        return free_blocks

    def create_event(self, title, start_iso, end_iso, description="", calendar_id="primary", rationale=""):
        eid = self._next_id()
        ev = {
            "id": eid, "title": title, "start_iso": start_iso, "end_iso": end_iso,
            "description": description, "rationale": rationale,
            "calendar_id": calendar_id, "all_day": False,
        }
        self._events[eid] = ev
        return {"id": eid, "title": title, "start_iso": start_iso, "end_iso": end_iso, "status": "created"}

    def modify_event(self, event_id, title=None, start_iso=None, end_iso=None, rationale=""):
        ev = self._events.get(event_id)
        if ev is None:
            return {"status": "not_found", "event_id": event_id, "modified": False}
        if title is not None: ev["title"] = title
        if start_iso is not None: ev["start_iso"] = start_iso
        if end_iso is not None: ev["end_iso"] = end_iso
        if rationale: ev["rationale"] = rationale
        return {"status": "modified", "event_id": event_id, "modified": True,
                **{k: ev[k] for k in ("title", "start_iso", "end_iso")}}

    def delete_event(self, event_id, rationale=""):
        if event_id in self._events:
            del self._events[event_id]
            return {"status": "deleted", "event_id": event_id, "deleted": True, "found": True}
        return {"status": "not_found", "event_id": event_id, "deleted": False, "found": False}


# ---------------------------------------------------------------------------
# Mock data for canvas.* / reranker.* / study.* (no real backend possible here).
# ---------------------------------------------------------------------------

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


def _seed_events() -> list[dict]:
    """Initial events the demo starts with — gives users something to list/modify/delete out of the box."""
    return [
        {"id": "evt_001", "title": "CS 3704 lecture", "start_iso": "2026-05-06T10:00:00+00:00", "end_iso": "2026-05-06T11:00:00+00:00", "calendar_id": "primary"},
        {"id": "evt_002", "title": "MATH 2114 office hours", "start_iso": "2026-05-06T15:00:00+00:00", "end_iso": "2026-05-06T16:00:00+00:00", "calendar_id": "primary"},
        {"id": "evt_003", "title": "PHYS 2306 lab", "start_iso": "2026-05-07T13:00:00+00:00", "end_iso": "2026-05-07T15:00:00+00:00", "calendar_id": "primary"},
    ]


def init_state() -> dict:
    """Per-session state — held in gr.State."""
    return {
        "backend": InMemoryCalendarBackend(seed_events=_seed_events()),
        "tool_log": [],
    }


def apply_tool(tool_name: str, args: dict, state: dict) -> tuple[Any, dict]:
    """Pure-ish tool dispatch: given (name, args, state), produce (result, possibly-mutated-state).

    Calendar tools mutate state["backend"] in place; canvas/reranker/study tools are stateless mocks.
    """
    backend: InMemoryCalendarBackend = state["backend"]

    if tool_name == "calendar.create_event":
        return backend.create_event(**args), state
    if tool_name == "calendar.delete_event":
        return backend.delete_event(**args), state
    if tool_name == "calendar.modify_event":
        return backend.modify_event(**args), state
    if tool_name == "calendar.list_events":
        return {"items": backend.list_events(**args)}, state
    if tool_name == "calendar.find_free_blocks":
        return {"blocks": backend.find_free_blocks(**args)}, state

    # Canvas tools — stateless mocks.
    if tool_name == "canvas.get_assignments":
        return {"items": _MOCK_ASSIGNMENTS}, state
    if tool_name == "canvas.get_course":
        cid = int(args.get("course_id", 1))
        return next((c for c in _MOCK_COURSES if c["id"] == cid), _MOCK_COURSES[0]), state
    if tool_name == "canvas.get_grades":
        return {"items": [{"course": c["code"], "grade": "A-", "score": 91.2} for c in _MOCK_COURSES]}, state
    if tool_name == "canvas.get_syllabus":
        return {"course_id": args.get("course_id", 1), "syllabus": "MWF 10–10:50 McBryde 113. Final TBD."}, state
    if tool_name == "canvas.get_todo":
        return {"items": [{"title": "Submit PM4", "course": "CS 3704", "due": "2026-05-08T23:59:00Z"}]}, state
    if tool_name == "canvas.list_announcements":
        return {"items": [{"course": "CS 3704", "title": "PM4 rubric posted"}, {"course": "MATH 2114", "title": "Final: McBryde 100"}]}, state
    if tool_name == "canvas.list_courses":
        return {"items": _MOCK_COURSES}, state
    if tool_name == "canvas.list_planner_items":
        return {"items": [{"title": a["title"], "course": a["course"], "due": a["due_at"]} for a in _MOCK_ASSIGNMENTS]}, state

    if tool_name == "reranker.priority_hint":
        return {"ranked": _MOCK_ASSIGNMENTS, "rationale": "sorted by due date"}, state
    if tool_name == "study.exam_bracket":
        return {"bracket": [{"phase": "deep_prep", "blocks_min": 240}, {"phase": "review", "blocks_min": 150}, {"phase": "light_cram", "blocks_min": 90}]}, state
    if tool_name == "study.recommend_block_size":
        return {"recommended_block_min": 90}, state
    if tool_name == "study.semester_schedule":
        return {"weeks": [{"week": 1, "study_hours": 9}, {"week": 14, "study_hours": 22}]}, state
    if tool_name == "study.spaced_schedule":
        return {"intervals_days_before_exam": [9, 4, 1]}, state

    return {"ok": True, "note": f"mock {tool_name}", "args": args}, state


# ---------------------------------------------------------------------------
# Calendar pane rendering — HTML week-view of state["backend"]._events.
# ---------------------------------------------------------------------------

def render_calendar_html(state: dict) -> str:
    backend: InMemoryCalendarBackend = state["backend"]
    events = backend.list_events()
    if not events:
        return (
            '<div style="padding:20px;color:#9ca3af;font-size:0.85rem;text-align:center;">'
            'Calendar is empty. Try: "Schedule a study block tomorrow 3-5pm".'
            '</div>'
        )

    # Group by date
    by_date: dict[str, list[dict]] = {}
    for ev in events:
        try:
            d = dt.datetime.fromisoformat(str(ev["start_iso"]).replace("Z", "+00:00"))
            key = d.strftime("%a %b %d")
        except Exception:
            key = "Unknown"
        by_date.setdefault(key, []).append(ev)

    html_parts = ['<div style="padding:8px;font-size:0.82rem;line-height:1.5;">']
    html_parts.append(
        f'<div style="color:#9ca3af;font-size:0.72rem;margin-bottom:8px;">'
        f'{len(events)} event{"s" if len(events) != 1 else ""} in session calendar'
        f'</div>'
    )
    for date_key, day_events in by_date.items():
        html_parts.append(
            f'<div style="margin-bottom:10px;">'
            f'<div style="color:#d63e36;font-weight:600;font-size:0.78rem;'
            f'border-bottom:1px solid #2e2e38;padding-bottom:3px;margin-bottom:5px;">'
            f'{date_key}</div>'
        )
        for ev in day_events:
            try:
                s = dt.datetime.fromisoformat(str(ev["start_iso"]).replace("Z", "+00:00"))
                e = dt.datetime.fromisoformat(str(ev["end_iso"]).replace("Z", "+00:00"))
                tspan = f'{s.strftime("%H:%M")}–{e.strftime("%H:%M")}'
            except Exception:
                tspan = ""
            html_parts.append(
                f'<div style="background:#18181f;border:1px solid #2e2e38;'
                f'border-left:3px solid #d63e36;border-radius:4px;'
                f'padding:6px 8px;margin-bottom:4px;">'
                f'<div style="color:#d4d4db;font-weight:500;">{ev.get("title", "(untitled)")}</div>'
                f'<div style="color:#9ca3af;font-size:0.72rem;">'
                f'<code style="background:#0a0a0b;padding:1px 4px;border-radius:2px;">{ev.get("id","?")}</code> '
                f'· {tspan}</div>'
                f'</div>'
            )
        html_parts.append('</div>')
    html_parts.append('</div>')
    return "".join(html_parts)


# ---------------------------------------------------------------------------
# Model loading (must remain — runs at HF Space build time on ZeroGPU).
# ---------------------------------------------------------------------------

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
            do_sample=True, temperature=1.0, top_p=0.95, top_k=64,
            max_new_tokens=MAX_NEW_TOKENS,
            pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(out[0, input_ids.shape[1]:], skip_special_tokens=False)


# ---------------------------------------------------------------------------
# Chat function — bound to gr.Blocks layout.
# Signature: (message, history, state) -> (history, state, calendar_html).
# Order MUST match the Blocks .click() outputs binding below.
# ---------------------------------------------------------------------------

def chat(message: str, history: list, state: dict | None):
    if state is None:
        state = init_state()
    if not (message or "").strip():
        return history or [], state, render_calendar_html(state)

    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history or []:
        if isinstance(h, dict):
            msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        elif isinstance(h, (list, tuple)) and len(h) >= 2:
            if h[0]: msgs.append({"role": "user", "content": h[0]})
            if h[1]: msgs.append({"role": "assistant", "content": h[1]})
    msgs.append({"role": "user", "content": message})

    tool_log: list[dict] = []
    raw = ""
    MAX_CALLS_PER_TURN = 2
    for _ in range(MAX_TURNS):
        raw = generate_step(msgs)
        calls = parse_tool_calls(raw)[:MAX_CALLS_PER_TURN]
        msgs.append({"role": "assistant", "content": raw})
        if not calls:
            break
        for call in calls:
            already = any(
                t["tool"] == call["tool"] and t["args"] == call["args"]
                for t in tool_log
            )
            if already:
                continue
            result, state = apply_tool(call["tool"], call["args"], state)
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
        reply = f"{final}\n\n<details><summary>🔧 {label} (mock data — session-local state)</summary>\n\n{table}\n\n</details>"
    else:
        reply = final

    new_history = (history or []) + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ]
    state["tool_log"].extend(tool_log)
    return new_history, state, render_calendar_html(state)


# ---------------------------------------------------------------------------
# UI: Blocks layout (chat left, calendar right) + 4 accordions of examples.
# ---------------------------------------------------------------------------

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
.gradio-container { max-width: 1280px !important; padding: 20px 16px !important; }
.block { box-shadow: none !important; border-radius: 8px !important; }
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
.bot .message table { font-size: 0.75rem !important; border-collapse: collapse !important; width: 100% !important; margin-top: 6px; }
.bot .message th, .bot .message td { padding: 3px 8px !important; border: 1px solid #2e2e38 !important; text-align: left !important; }
.bot .message th { background: #111114 !important; color: #9ca3af !important; font-weight: 500 !important; }
.bot .message details summary { cursor: pointer; color: #6b7280; font-size: 0.78rem; user-select: none; }
.input-row textarea { border-radius: 6px !important; font-size: 0.875rem !important; min-height: 48px !important; }
/* Gradio renders elem_classes directly on the <button>, NOT a wrapper div.
   Live DOM inspection: <button class="sm secondary example-btn svelte-...">.
   Selector must be `button.example-btn`, not `.example-btn button`. */
button.example-btn {
    border-radius: 16px !important;
    font-size: 0.74rem !important;
    padding: 3px 10px !important;
    border: 1px solid #2e2e38 !important;
    background: #18181f !important;
    color: #d4d4db !important;
    text-align: left !important;
    white-space: normal !important;
    min-height: auto !important;
}
button.example-btn:hover { border-color: #d63e36 !important; background: #1f1010 !important; color: #ffffff !important; }
.description { font-size: 0.82rem !important; line-height: 1.6 !important; color: #9ca3af !important; }
#calendar-pane { background: #111114; border: 1px solid #2e2e38; border-radius: 8px; min-height: 440px; max-height: 600px; overflow-y: auto; }
"""

DESCRIPTION_MD = """
Fine-tuned **Gemma-4-E2B-IT** (DPO · β=0.1 · 181 trajectories · 90.3% reward accuracy) — speaks the native Gemma-4 tool protocol for **18 tools** across 4 families:

`canvas.*` assignments · grades · syllabi · planner &nbsp;|&nbsp; `calendar.*` scheduling · free blocks &nbsp;|&nbsp; `reranker.*` priority hints &nbsp;|&nbsp; `study.*` exam prep · spaced repetition

> ⚠️ **Mock data** — no Canvas credentials in this Space. Calendar uses a **session-local in-memory backend** (mirrors `canvas_sdk.backends.calendar_adapter.InMemoryCalendarBackend`) so create/delete/modify/list round-trips behave coherently within a single browser tab. For live data: `pip install canvas-sdk[autodownload]`.
> ⏱ Cold-start after inactivity ~30 s (ZeroGPU). Subsequent responses are fast.

[Model](https://huggingface.co/kleinpanic93/canvas-calendar-agent-v7-dpo) · [Dataset](https://huggingface.co/datasets/kleinpanic93/canvas-calendar-preferences-v7) · [Collection](https://huggingface.co/collections/kleinpanic93/canvas-calendar-agent-v30-69fa6462f697e0342b21dfe0) · [GitHub](https://github.com/kleinpanic/CS3704-Canvas-Project) · [Docs](https://kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/method.html)
"""


CANVAS_EXAMPLES = [
    "List my courses",
    "Tell me about my CS 3704 course",
    "What assignments do I have due this week?",
    "What are my current grades?",
    "Show me the syllabus for MATH 2114",
    "What's on my Canvas todo list?",
    "Any new announcements in my courses?",
    "What's on my planner this week?",
]
CALENDAR_EXAMPLES = [
    "What's on my calendar this week?",
    "Find a 2-hour free block tomorrow afternoon",
    "Schedule a study block tomorrow 3-5pm",
    "Move my 2pm event to 4pm",
    "Cancel my 3pm meeting",
]
STUDY_EXAMPLES = [
    "Build a study bracket for the May 12 final",
    "What study block size do you recommend for me?",
    "Build a semester study schedule",
    "Plan spaced repetition for Linear Algebra final",
]
RERANKER_EXAMPLES = [
    "Rank my todos by priority",
]


with gr.Blocks(theme=THEME, css=CUSTOM_CSS, title="Canvas Calendar Agent") as demo:
    gr.Markdown("# Canvas Calendar Agent")
    gr.Markdown(DESCRIPTION_MD, elem_classes=["description"])

    state = gr.State(value=init_state)

    with gr.Row(equal_height=True):
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                type="messages",
                height=440,
                show_label=False,
                avatar_images=None,
            )
            with gr.Row(elem_classes=["input-row"]):
                msg = gr.Textbox(
                    placeholder="Ask the agent anything…",
                    show_label=False,
                    scale=8,
                    lines=1,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)
        with gr.Column(scale=2):
            gr.Markdown("### Calendar (session-local)")
            calendar_html = gr.HTML(
                value=render_calendar_html(init_state()),
                elem_id="calendar-pane",
            )

    gr.Markdown("### Try one of the 18 tools")
    with gr.Row():
        with gr.Column():
            gr.Markdown("**Calendar (5)**")
            for ex in CALENDAR_EXAMPLES:
                btn = gr.Button(ex, elem_classes=["example-btn"], size="sm")
                btn.click(lambda x=ex: x, outputs=msg, api_name=False)
            gr.Markdown("**Reranker (1)**")
            for ex in RERANKER_EXAMPLES:
                btn = gr.Button(ex, elem_classes=["example-btn"], size="sm")
                btn.click(lambda x=ex: x, outputs=msg, api_name=False)
        with gr.Column():
            gr.Markdown("**Canvas (8)**")
            for ex in CANVAS_EXAMPLES:
                btn = gr.Button(ex, elem_classes=["example-btn"], size="sm")
                btn.click(lambda x=ex: x, outputs=msg, api_name=False)
        with gr.Column():
            gr.Markdown("**Study (4)**")
            for ex in STUDY_EXAMPLES:
                btn = gr.Button(ex, elem_classes=["example-btn"], size="sm")
                btn.click(lambda x=ex: x, outputs=msg, api_name=False)

    # Wire send button + Enter-key submit. Outputs order MUST match chat() return:
    # (history, state, calendar_html).
    send_btn.click(
        fn=chat,
        inputs=[msg, chatbot, state],
        outputs=[chatbot, state, calendar_html],
        api_name=False,
    ).then(lambda: "", outputs=msg, api_name=False)

    msg.submit(
        fn=chat,
        inputs=[msg, chatbot, state],
        outputs=[chatbot, state, calendar_html],
        api_name=False,
    ).then(lambda: "", outputs=msg, api_name=False)


if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
