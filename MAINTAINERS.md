# Maintainers

CS3704 Canvas Project — maintained by a small team (Spring 2026).

## Roles

| Role | Person | Responsibility |
|------|--------|----------------|
| Owner | Klein Panic | Final approval, branch protection, release authority, security advisories |
| Maintainer | Williammm23 | Grades screen, canvas_tui feature development, RMP integration |
| Maintainer | pjie22 | Documentation, implementation reviews, onboarding docs |
| Maintainer | 802797liu | Test coverage, filter/query improvements, CI health |

## Working Agreement

- Work starts from an Issue
- Branch from `main`: `feature/`, `fix/`, `docs/`, `test/`, `chore/`, `refactor/`, `hotfix/`
- Open PRs early, keep scope tight
- CI must pass (tests + coverage) before merge
- GPG-signed commits required on `main` (enforced via branch protection + Phase 6 supply-chain hardening)
- Do not force-push protected `main`

## What Blocks a PR

Tests, coverage, and CI (ruff, mypy, CodeQL) must all pass before merge.

## Test Requirements

- All new code must have tests
- Run `make test` locally before pushing
- Coverage threshold: 80% (bypass with `#no-coverage-check` in PR body for justified exceptions)

## Review SLAs

| Item | Target |
|------|--------|
| Pull request review | 1 week from opening |
| Issue triage | 2 weeks from opening |
| Security advisory response | 48 hours (see SECURITY.md) |

SLA clock pauses when waiting for contributor response.

## Scope per Maintainer

| Maintainer | Primary Scope |
|------------|---------------|
| Klein Panic (Owner) | Final merge authority, branch protection, release tags, security advisories, supply-chain config |
| Williammm23 | Grades screen, canvas_tui feature development, RMP integration |
| pjie22 | Documentation, implementation reviews, onboarding docs |
| 802797liu | Test coverage, filter/query improvements, CI health |

## Escalation Path

1. Assign the issue or PR to the relevant maintainer.
2. No response within SLA → ping the Owner (`@kleinpanic`) in the issue thread.
3. Disagreement on direction → Owner decision is final; rationale recorded in the Decision Log below.

## Decision Log

Notable maintainer decisions with date and rationale.

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-06 | Clean-room SDK rewrite (Phase 0) | Remove canvasapi-derived port to establish clear provenance for public contribution; eliminates license ambiguity |
| 2026-05-06 | Piiranha v1 for PII scrub pipeline | Best open-source NER model for PII detection in educational context; canvas-anon Docker enables CI-reproducible scrubbing |
| 2026-05-06 | GPG-signed commits required on main | Supply-chain hardening; matches OSSF Scorecard criteria; replaces the earlier class-project policy of no-signing-required |
| 2026-05-06 | CANVAS_BASE_URL required at all entry points | Fork-friendliness; removes VT-specific defaults so any institution can use the project without code edits (Phase 5) |
| 2026-05-06 | SHA-pin all third-party Actions (Phase 6) | Prevents tag-mutation supply-chain attacks; matches harden-runner egress-audit pattern used by smolagents, OpenHands |

## Core Architecture

See `docs/project/DEVELOPER_GUIDE.md` for setup instructions.
See `docs/QUICKSTART.md` for the 10-minute onboarding guide.
