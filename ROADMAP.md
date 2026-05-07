# Roadmap — Canvas Tracker

## Milestones

| Milestone | Status | Goal |
|-----------|--------|------|
| v1.0 Public Demo Surface | Complete | Chrome extension + TUI + HF Space + GH Pages + Worker proxy + DPO model |
| v2.0 Public-Contribution Hardening | In Progress | Safe, frictionless outside contribution: PII-clean pipeline, SOTA CI/CD, polished SDK, professional repo |

---

## v2.0 Public-Contribution Hardening — Phase Progress

| Phase | Name | Status | Goal |
|-------|------|--------|------|
| 0 | Clean-Room SDK Rewrite | Complete | Replace canvasapi-derived port with pure-stdlib CanvasClient |
| 1 | SDK Migration & v2.0.0 Release | Complete | Wire new CanvasClient into all callers; delete port; ship v2.0.0 |
| 2 | Dataset Pipeline PII Lockdown | Complete | Piiranha v1 scrub; course anonymization; --inspect flag |
| 3 | CI Dataset Validation Workflow | Complete | Gate data/collab/ merges on schema + PII CI checks |
| 4 | Dedicated PII-Scrub HF Space | Complete | Stand up canvas-pii-scrub Space; wire --scrub-via-space |
| 5 | Standalone Release & Fork-Friendly Config | Complete | CANVAS_BASE_URL required; no VT defaults; fork CI guards |
| 6 | CI/CD Hardening + Supply-Chain Security | Complete | SHA-pinned actions; harden-runner; OSSF Scorecard; SBOM/SLSA |
| 7 | HF Space UI Upgrade | Complete | gr.Examples; hero strip; TextIteratorStreamer; smoke test |
| 8 | TUI/Extension SDK Discipline | Complete | Refactor canvas_tui; keybinding registry; SDK-layer tests |
| 9 | Badges + Devcontainer + Codecov | Complete | Live Codecov %; PyPI badges; devcontainer; README badge row |
| 10 | Professional/SOTA Polish | In Progress | examples/; QUICKSTART; public ROADMAP; SECURITY/MAINTAINERS |
| 11 | Cleanup Pass | Complete | Dead code removal; foot-guns; AI-tell docstrings; tools/clean.sh |

---

## Current Focus

**Phase 10: Professional/SOTA Polish** — adding runnable `examples/` scripts,
`docs/QUICKSTART.md` for 10-minute onboarding, this public-facing `ROADMAP.md`, an
expanded `SECURITY.md` with disclosure timelines and scope, the all-contributors bot,
and `.editorconfig`. Goal: any newcomer can go from clone to working TUI in under
10 minutes, and any security researcher knows exactly how to reach us.

---

## What's Next

After Phase 10 closes:

- **Milestone audit** (`/gsd-audit-milestone`) — verify all 12 acceptance criteria
  across Phases 0-11 against the live repo.
- **Milestone close** (`/gsd-complete-milestone`) — tag v2.0.0, update CHANGELOG, cut release.
- **v3.0 planning** — multi-institution support, Windows/macOS TUI matrix, Conda-forge feedstock.

---

## Contributing

- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, branch naming, PR process
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — 10-minute onboarding
- [docs/contributing-data.md](docs/contributing-data.md) — how to contribute Canvas trajectory data
- [examples/](examples/) — runnable quickstart scripts
