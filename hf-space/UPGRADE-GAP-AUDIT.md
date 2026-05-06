# HF Space Upgrade — Gap Audit

Audit performed during the `feat/hf-space-state-calendar-upgrade` PR. Captures the state of `hf-space/app.py` as deployed (commit `8210d61`-era) and the deltas applied in this PR.

## Why mocks at all?

The Space has no Canvas credentials and no Google Calendar OAuth. It's a public demo on ZeroGPU; persistent or per-user state would require backing storage that doesn't exist here. So tool results have to be synthetic.

What this PR fixes is **coherence**: the previous mocks were stateless module-level dicts. `calendar.create_event` always returned `evt_001`; `calendar.list_events` always returned the same one event; `calendar.delete_event` reported `deleted: true` but the next `list_events` showed the deleted event still present. A user trying any multi-step flow (`create → list`, or `delete → list`) saw an obviously broken loop.

The fix: a per-session `gr.State` wrapping an `InMemoryCalendarBackend` (matching the SDK's `CalendarBackend` contract) that holds events in a mutable dict keyed by event_id with an auto-incrementing counter. Calendar tools route through that backend so create/modify/delete/list round-trips behave coherently for the duration of a single browser tab.

## Per-tool table (all 18)

| # | Tool                          | Surfaced as example before? | Mock was stateful? | SDK reuse? | What this PR does |
|---|-------------------------------|-----------------------------|--------------------|------------|-------------------|
| 1 | `canvas.list_courses`         | no                          | n/a (read-only)    | no — Space has no Canvas creds          | Add example button. Mock unchanged (read-only is fine stateless). |
| 2 | `canvas.get_course`           | no                          | n/a                | no                                       | Add example button. |
| 3 | `canvas.get_assignments`      | yes                         | n/a                | no                                       | Keep example, no behavioural change. |
| 4 | `canvas.get_grades`           | yes                         | n/a                | no                                       | Keep. |
| 5 | `canvas.get_syllabus`         | no                          | n/a                | no                                       | Add example button. |
| 6 | `canvas.get_todo`             | no                          | n/a                | no                                       | Add example button. |
| 7 | `canvas.list_announcements`   | yes                         | n/a                | no                                       | Keep. |
| 8 | `canvas.list_planner_items`   | no                          | n/a                | no                                       | Add example button. |
| 9 | `calendar.create_event`       | yes                         | **NO — broken**    | **YES — added InMemoryCalendarBackend to SDK** | Routes through `InMemoryCalendarBackend.create_event`; assigns auto-incrementing `evt_NNN`; appears in subsequent `list_events`. |
| 10 | `calendar.delete_event`       | no                          | **NO — broken**    | YES                                      | Routes through `InMemoryCalendarBackend.delete_event`; mutates state; returns `{deleted, found}`. |
| 11 | `calendar.modify_event`       | no                          | **NO — broken**    | YES                                      | Routes through `InMemoryCalendarBackend.modify_event`; mutates by id. |
| 12 | `calendar.list_events`        | no                          | **NO — broken**    | YES                                      | Routes through `InMemoryCalendarBackend.list_events`; reflects all prior mutations. |
| 13 | `calendar.find_free_blocks`   | yes                         | NO                 | YES                                      | Routes through `InMemoryCalendarBackend.find_free_blocks`; computed from actual events. |
| 14 | `reranker.priority_hint`      | yes                         | n/a                | no — would need real reranker model       | Keep mock. |
| 15 | `study.exam_bracket`          | yes                         | n/a                | no                                       | Keep mock. |
| 16 | `study.recommend_block_size`  | no                          | n/a                | no                                       | Add example button. |
| 17 | `study.semester_schedule`     | no                          | n/a                | no                                       | Add example button. |
| 18 | `study.spaced_schedule`       | yes                         | n/a                | no                                       | Keep. |

Net change in surfaced examples: **8 → 18**.

## SDK-reuse decision

The advisor brief said "tool dispatch becomes `result = ListEvents(adapter).run(args)` etc." That literal API does not exist:

1. `canvas_sdk.agent_tools.calendar_tools.ListEvents` uses `@staticmethod def call(args)`, not `.run(args)`.
2. The static `call(args)` resolves the adapter via `CalendarAdapter.from_config()`, which calls `from canvas_tui.config import load_config` — `canvas_tui` is a separate package not installable from PyPI and not in `hf-space/requirements.txt`.
3. `hf-space/requirements.txt` doesn't include `canvas-sdk`, and the deploy workflow only uploads the `hf-space/` directory to the Space (not `src/sdk/`).

The achievable form of "SDK reuse" is therefore:
- **SDK side:** add `InMemoryCalendarBackend` to `src/sdk/canvas_sdk/backends/calendar_adapter.py` so the SDK gains a real, in-memory backend matching the `CalendarBackend` abstract contract — with its own round-trip self-test under `if __name__ == "__main__"`. Anyone with `canvas-sdk` installed can now use it.
- **Space side:** inline a copy of the same class into `hf-space/app.py`. The contract is identical to the SDK class. Both stay in lockstep on contract — not on import.

This is documented as a deviation in the SUMMARY.md (Rule 3 — blocked dependency path).

## Backend semantics: `propose_*` vs immediate mutation

The abstract `CalendarBackend.propose_modification` and `propose_deletion` contract was designed for the TUI's confirmation flow: it returns a pending stub the user must approve before the calendar mutates. That's the right contract for a real user-facing TUI.

The Space, in contrast, is a single-session demo with no confirmation UI — if `delete_event` returned a pending stub, the calendar pane would not update and users would think the agent was broken. So the `InMemoryCalendarBackend` exposes **both**: `propose_modification` / `propose_deletion` (for protocol compatibility) and `modify_event` / `delete_event` (immediate mutation). The Space wires the calendar tools to the immediate-mutation methods.

## What this PR does NOT do (deferred)

- Persist state across sessions (would need HF Space persistent storage).
- Wire `canvas.*` tools to a real Canvas instance (no creds in a public Space).
- Fine-grained `find_free_blocks` constraints (quiet hours, holidays, recurring busy windows).
- Surface tool errors to users — currently mocks always succeed.
- Replace the 4 study-tool mocks with the real algorithms from `canvas_tui.study_planner` (those depend on local config + grade data).
