# Maintainers

CS3704 Canvas Project — maintained by a small team (Spring 2026).

## Roles

| Role | Person | Responsibility |
|---|---|---|
| Owner | Klein Panic | Final approval, branch protection, release authority |
| Maintainer | Williammm23 | Grades screen, feature development |
| Maintainer | pjie22 | Documentation, implementation reviews |
| Maintainer | 802797liu | Test coverage, filter/query improvements |

## Working Agreement

- Work starts from an Issue
- Branch from `main`: `feature/`, `fix/`, `docs/`, `test/`, `chore/`, `refactor/`, `hotfix/`
- Open PRs early, keep scope tight
- CI must pass (tests + coverage) before merge
- **No signed commits required** — simplified for class project scale
- Do not force-push protected `main`

## What Blocks a PR

Only tests and coverage checks block merge. Linting, type checking, and documentation are advisory and handled via AI fixup workflows post-merge.

## Test Requirements

- All new code must have tests
- Run `make test` locally before pushing
- Coverage threshold: 80% (bypass with `#no-coverage-check` in PR body)

## Core Architecture

See `docs/project/VISUAL-AUDIT.md` for the advancement plan and `docs/project/DEVELOPER_GUIDE.md` for setup instructions.

For the shared-core architecture that enables the planned browser extension, see the Phase 2 refactor plan in `docs/project/VISUAL-AUDIT.md`.