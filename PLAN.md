# PLAN.md

## Task
P0.1: Split monolith into src/ package modules

## Subtasks
- [ ] Audit current `canvas-tui.py` structure and map functions/classes to target modules.
- [ ] Create `src/canvas_tui/` package layout (`app.py`, `config.py`, `api.py`, `models.py`, `state.py`, `screens/`, `widgets/`, `utils.py`, `__init__.py`).
- [ ] Move configuration/state/http/helpers/fetch logic into new modules with import-safe boundaries.
- [ ] Move Textual UI components into `screens/` and `widgets/` and rewire `CanvasTUI` in `app.py`.
- [ ] Add compatibility launcher script and update packaging/build files (`pyproject.toml`, `Makefile`).
- [ ] Run lint/smoke verification and fix regressions.

## State
Status: IN_PROGRESS
Current subtask: Audit current `canvas-tui.py` structure and map functions/classes to target modules.
Notes:
- Lobster workflow invocation currently fails with: `Unsupported condition: $LOBSTER_ARG_involvement == "heavy"`.
- Proceeding with equivalent manual Plan→Execute→Verify flow in repo.
