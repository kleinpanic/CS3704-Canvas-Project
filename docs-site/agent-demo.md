# Canvas Calendar Agent — Gemma4 Demo

The **Canvas Calendar Agent** is a tutor-style assistant that lives inside this
project's TUI and browser extension. It uses a **fine-tuned Gemma4-E2B-IT**
model (SFT + DPO) running behind an OpenAI-compatible endpoint, and drives a
registry of 18 Canvas/Calendar/Study tools to answer questions about a
student's coursework, plan study blocks, and surface late-submission policies.

This page documents how the harness is wired together, how to run the demo,
and what a realistic interaction looks like.

---

## What it does

Given a natural-language question, the agent:

1. Pulls live data from Canvas (assignments, todo, announcements, grades).
2. Optionally consults the user's calendar (Google or `.ics`) to find free
   blocks.
3. Returns a short, action-oriented answer — bullet lists, deadlines, study
   suggestions — without fabricating course names or due dates.

It will **not** call a tool unless the question actually requires live data,
and it will **not** include any tool-call markup in its final reply.

---

## Architecture

```text
+------------+     run(user_msg)     +-------------------+
|  CanvasTUI |  ------------------>  |    CanvasAgent    |
|     /      |                       |  (agent loop)     |
|  Extension |  <------------------  +---------+---------+
+------------+      final answer               |
                                               | chat(messages, tools)
                                               v
                                  +----------------------------+
                                  |       Gemma4Backend        |
                                  |  OpenAI-compatible client  |
                                  +-------------+--------------+
                                                |
                                                v
                                  +----------------------------+
                                  |  vLLM @ localhost:18080    |
                                  |   fine-tuned Gemma4-E2B-IT |
                                  +-------------+--------------+
                                                |
                          assistant content (with <|tool_call> blocks)
                                                |
                                                v
                                +-----------------------------+
                                |  tool_parser.parse_tool_calls |
                                +--------------+--------------+
                                               |
                                               v
                                +-----------------------------+
                                | agent_tools.dispatch(name,args) |
                                +--------------+--------------+
                                               |
                            +------------------+------------------+
                            |                  |                  |
                            v                  v                  v
                      canvas_tools     calendar_tools       study_tools
                      (Canvas API)     (Google / ICS)       (planning)
```

The full handshake on a single turn:

1. `CanvasAgent.run()` builds the system prompt (with the tool catalog
   inlined) and posts the message list to `Gemma4Backend.chat()`.
2. The backend hits the OpenAI-compatible `/v1/chat/completions` endpoint and
   returns the assistant content as a string.
3. `tool_parser.parse_tool_calls()` extracts every
   `<|tool_call>call:NAME{ARGS}<tool_call|>` block.
4. Each call is dispatched through `canvas_sdk.agent_tools.dispatch()`. The
   result is JSON-encoded and re-injected as a
   `<|tool_response>response:NAME{value:<|"|>...<|"|>}<tool_response|>` message.
5. Loop until the model produces a turn with no tool calls (final answer) or
   `agent_max_turns` is reached.

---

## Tool surface

The 18-tool registry already shipped on the SDK; the agent harness just makes
it agentic. Categories:

| Group | Examples |
|---|---|
| Canvas | `canvas.list_courses`, `canvas.get_assignments`, `canvas.get_todo`, `canvas.get_grades`, `canvas.get_syllabus`, `canvas.list_announcements`, `canvas.list_planner_items`, `canvas.get_course` |
| Calendar | `calendar.list_events`, `calendar.find_free_blocks`, `calendar.schedule_block`, `calendar.delete_block` |
| Study | `study.suggest_block`, `study.weekly_summary`, `study.deadline_pressure` |
| Reranker | `reranker.rerank_assignments`, `reranker.priority_score` |

Schemas are exposed via `canvas_sdk.agent_tools.get_schemas()` and forwarded
both as the OpenAI `tools` field and as a bullet list inside the system
prompt (Gemma4's training data prefers in-prompt catalogs).

---

## Installation

```bash
pip install -e ./sdk
# httpx is now a hard dependency of canvas-sdk; no extra install needed
```

Set environment variables for the inference endpoint and Canvas:

```bash
export LLM_ENDPOINT="http://localhost:18080/v1"
export LLM_MODEL="google/gemma-4-e2b-it"     # or your fine-tuned tag
export OPENAI_API_KEY="forge"                # spark-proxy / forge default
export CANVAS_BASE_URL="https://canvas.vt.edu"
export CANVAS_TOKEN="..."                    # personal access token
```

---

## Quickstart

```python
from canvas_sdk import CanvasAgent, Gemma4Backend

backend = Gemma4Backend(
    endpoint="http://localhost:18080/v1",
    model="google/gemma-4-e2b-it",
    api_key="forge",
)
agent = CanvasAgent(backend, max_turns=8)

print(agent.run("What assignments are due this week?"))
```

Or run the bundled script:

```bash
python scripts/demo_agent.py
```

---

## Example transcript

A realistic three-turn interaction the model produces against a live Canvas
account during finals week:

**User:**

> I have CS 3704 and STAT 3704 midterms next week. Can you help me plan study
> blocks around what's already on my calendar?

**Agent (turn 1, internal):**

```text
<|tool_call>call:canvas.get_todo{}<tool_call|>
<|tool_call>call:calendar.find_free_blocks{horizon_days: 7, min_minutes: 60}<tool_call|>
```

**Tool results (truncated):**

```json
[
  {"course": "CS 3704", "assignment": "Midterm 2", "due_at": "2026-05-12T17:00:00-04:00"},
  {"course": "STAT 3704", "assignment": "Midterm", "due_at": "2026-05-13T15:00:00-04:00"},
  {"course": "ENGL 1106", "assignment": "Essay 4 draft", "due_at": "2026-05-09T23:59:00-04:00"}
]
```

```json
[
  {"start": "2026-05-06T09:00", "end": "2026-05-06T11:30", "duration_min": 150},
  {"start": "2026-05-07T13:00", "end": "2026-05-07T16:00", "duration_min": 180},
  {"start": "2026-05-09T10:00", "end": "2026-05-09T12:00", "duration_min": 120}
]
```

**Agent (turn 2, internal):**

```text
<|tool_call>call:study.suggest_block{course: <|"|>CS 3704<|"|>, deadline: <|"|>2026-05-12T17:00<|"|>, total_minutes: 360}<tool_call|>
<|tool_call>call:study.suggest_block{course: <|"|>STAT 3704<|"|>, deadline: <|"|>2026-05-13T15:00<|"|>, total_minutes: 300}<tool_call|>
```

**Agent (final answer):**

> Here's a plan for next week:
>
> - **Wed 5/6, 9:00-11:30** — CS 3704 review (graphs + DP, 2.5h)
> - **Thu 5/7, 13:00-16:00** — STAT 3704 problem set walkthrough (3h)
> - **Sat 5/9, 10:00-12:00** — finish ENGL essay draft (due 11:59pm)
> - **Sun 5/10, 14:00-17:00** — CS 3704 mock exam, timed (3h)
> - **Mon 5/11, 19:00-21:00** — STAT 3704 formula sheet + practice (2h)
>
> Both midterms are CS 3704 (Tue 5/12 5pm) and STAT 3704 (Wed 5/13 3pm).
> Want me to push these blocks to your Google Calendar?

The agent stays grounded in real assignment titles + timestamps (no
hallucinated due dates) because every fact in the answer came back through
`canvas.get_todo` or `calendar.find_free_blocks`.

---

## Tuning

| Config field | Default | Notes |
|---|---|---|
| `llm_endpoint` | `http://localhost:18080/v1` | spark-proxy router |
| `llm_model` | `google/gemma-4-e2b-it` | swap for your fine-tuned tag |
| `llm_api_key` | `forge` | most local routers ignore this |
| `agent_max_turns` | `8` | clamp on tool-loop depth |

`agent_max_turns` is bounded to `[1, 32]` by `Config._validate()`.

---

## Files

| Path | Role |
|---|---|
| `sdk/canvas_sdk/backends/gemma4_backend.py` | OpenAI-compatible HTTP client |
| `sdk/canvas_sdk/tool_parser.py` | Gemma4 `<|tool_call>` parser/formatter |
| `sdk/canvas_sdk/agent.py` | Agent loop + system prompt builder |
| `sdk/canvas_sdk/agent_tools/` | 18-tool registry (already shipped) |
| `src/canvas_tui/config.py` | LLM endpoint/model/key/turn-budget fields |
| `scripts/demo_agent.py` | CLI demo over three sample questions |
