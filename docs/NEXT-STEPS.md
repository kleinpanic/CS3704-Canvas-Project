# Remaining Work (Post-Migration)

## Priority 1 — Repository and Release
- [ ] Confirm final public GitHub repo name/owner and push `main`.
- [ ] Add GitHub Actions for lint + tests on PR.
- [ ] Add project badges (CI, Python version, license).
- [ ] Cut a `v0.1.0` tag after sanity validation.

## Priority 2 — Product Hardening
- [ ] Add contract tests for Canvas response schema drift.
- [ ] Add deterministic fixture pack for assignment/grade edge cases.
- [ ] Add retry telemetry counters for 429 + timeout handling.
- [ ] Add read-only safe mode and explicit error surfaces in CLI/TUI.

## Priority 3 — Browser Extension Parity
- [ ] Build extension shell that consumes shared domain contracts.
- [ ] Implement service-worker schedule + state sync parity.
- [ ] Add parity checklist against CLI features (dashboard, grades, due-soon, notifications).

## Priority 4 — Docs + DX
- [ ] Add architecture decision records (ADRs) for MVC + command strategy.
- [ ] Add onboarding guide for contributors (dev env, test matrix, coding standards).
- [ ] Add Mermaid render pipeline (optional `mmdc`) so SVGs can be generated automatically.

## Priority 5 — Academic Deliverables
- [ ] Convert architecture assets into slides for PM3/next checkpoint.
- [ ] Keep this repo aligned with the current CS3704 deliverable scope.
