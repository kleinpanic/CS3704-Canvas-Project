# CS3704 Canvas Project — Documentation Portal

Welcome to the team documentation portal. This site is built with MkDocs and deployed automatically on every push to `main`.

## Project Overview

**Canvas TUI** is a Canvas LMS productivity client with a Textual terminal interface today, and a documented path toward browser extension parity using a shared-core architecture.

> **Current status:** Feature-complete TUI in production use. Phase 2 (core architecture refactor) is the next milestone toward browser extension parity.

## Quick Links

| Resource | Link |
|----------|------|
| **Live TUI** | Run `pip install -e ".[dev]"` then `python -m canvas_tui` |
| **GitHub Repo** | [kleinpanic/CS3704-Canvas-Project](https://github.com/kleinpanic/CS3704-Canvas-Project) |
| **Open Issues** | [Issue Tracker](https://github.com/kleinpanic/CS3704-Canvas-Project/issues) |
| **Open PRs** | [Pull Requests](https://github.com/kleinpanic/CS3704-Canvas-Project/pulls) |
| **Dependabot** | [Dependency Updates](https://github.com/kleinpanic/CS3704-Canvas-Project/security/dependabot) |
| **Project Board** | [Sprint Board](https://github.com/users/kleinpanic/projects/5) |

## Architecture Documentation

- **[Architecture Overview](architecture.md)** — System design, MVC pattern, shared-core strategy, and extension roadmap
- **[Team Workflow](workflow.md)** — Branch strategy, PR process, CI gates, and contribution guidelines
- **[Project Roadmap](roadmap.md)** — Milestones, PM deliverables, and planned features

## Project Status

### Features Implemented
- TUI dashboard with course scores, due-soon items, grade trends, and completion gauges
- Per-course grade breakdown with what-if calculator, sort modes, and trend sparklines
- Calendar week view with 7-day grid
- Offline-first caching with SQLite persistence
- ICS export, Pomodoro timer, notification support
- Command bar filtering with query syntax

### Upcoming (Phase 2)
- Core architecture refactor: extract `CanvasClient` and `CacheBackend` interfaces
- Browser extension scaffolding with shared-domain architecture
- Deployment automation: PyPI upload, Chrome/Firefox extension stores

See [VISUAL-AUDIT.md](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/docs-site/VISUAL-AUDIT.md) for the full advancement plan.

## Deployment

| Environment | URL | Trigger |
|-------------|-----|---------|
| **Docs Site** | [kleinpanic.github.io/CS3704-Canvas-Project](https://kleinpanic.github.io/CS3704-Canvas-Project) | Every push to `main` |
| **PyPI Package** | `pip install canvas-tui` | On git tag push |

The docs site is built with MkDocs Material and deployed via GitHub Actions — no manual steps required.

## Team

| Role | Member | Responsibility |
|------|--------|----------------|
| **Owner** | Klein Panic | Architecture, CI/CD, releases |
| **Maintainer** | Williammm23 | Grades screen, feature development |
| **Maintainer** | pjie22 | Documentation, implementation reviews |
| **Maintainer** | 802797liu | Test coverage, filtering improvements |

See [CONTRIBUTORS.md](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/CONTRIBUTORS.md) for full credits and [MAINTAINERS.md](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/MAINTAINERS.md) for working agreements.

## CI/CD Pipeline

```
PR opened
  → Test (pytest, py3.11)
  → Coverage (80% threshold, bypass with #no-coverage-check)
  → Python Compat (3.11/3.12/3.13 smoke, informational)
  → PASS → review + merge
  → FAIL → AI fixup branch pushed (via Nemotron on DGX Spark)

Merged to main
  → Pages (docs site rebuild + deploy)
  → Auto Docs (Nemotron docstring generation, separate PR)
  → Security scan (CodeQL, informational)
```

## Security

See [SECURITY.md](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/SECURITY.md) for the security policy and [dependabot.yml](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/.github/dependabot.yml) for automated dependency updates.