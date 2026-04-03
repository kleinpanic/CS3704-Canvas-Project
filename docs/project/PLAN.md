# Plan: CanvasTUI-Proposal: phase 3 progressive startup hydration

| Field | Value |
|-------|-------|
| Task | a295177a-8217-439e-8829-16d45d562d3d |
| Complexity | moderate |
| Model Tier | standard (anthropic/claude-sonnet-4-5) |
| Agent | dev |
| Created | 2026-02-25T01:21:24-05:00 |

## Objective
CanvasTUI-Proposal: phase 3 progressive startup hydration

## Description
Implement phase-3 startup UX/perf: instant first paint from cached state, split refresh into fast core hydration and deferred grade hydration, and validate with tests + screenshots.

## Subtasks
- [x] 1 — Implement progressive startup flow: immediate cached first paint, avoid blocking loading modal when cache exists
- [x] 2 — Split refresh into fast core hydration (courses/items/announcements) then deferred grade hydration update
- [x] 3 — Improve startup/status messaging so user sees staged readiness and grade hydration progress
- [x] 4 — Add/adjust tests for new CLI/startup behavior where applicable
- [x] 5 — Verify + test (ruff, pytest, screenshot flow)

## Must-Haves
- [x] Primary objective achieved
- [x] No regressions
- [x] Tests pass

## Deviation Rules
Auto-fix bugs/blockers (rules 1-3). Ask Klein for architectural changes (rule 4).

## State
- **Status**: EXECUTED (READY FOR REVIEW)
- **Last Updated**: 2026-02-25T01:24:42-05:00
