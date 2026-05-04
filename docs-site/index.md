# CS3704 Canvas Project — Documentation Portal

Welcome to the team documentation portal. This site is built with MkDocs and deployed automatically on every push to `main`.

## Project Overview

**CS3704 Canvas Project** is a Canvas LMS productivity client with a mature Textual TUI, a live browser extension codebase, and a maintained documentation portal.

> **Current status:** `main` is the only long-term branch, the docs site deploys from `main`, and the browser extension now has a shared client/runtime architecture instead of ad hoc popup-to-background wiring.

## Quick Links

| Resource | Link |
|----------|------|
| **GitHub Repo** | [kleinpanic/CS3704-Canvas-Project](https://github.com/kleinpanic/CS3704-Canvas-Project) |
| **Open Issues** | [Issue Tracker](https://github.com/kleinpanic/CS3704-Canvas-Project/issues) |
| **Open PRs** | [Pull Requests](https://github.com/kleinpanic/CS3704-Canvas-Project/pulls) |
| **Project Board** | [Sprint Board](https://github.com/users/kleinpanic/projects/5) |
| **Docs Site** | [GitHub Pages](https://kleinpanic.github.io/CS3704-Canvas-Project/) |

## Architecture Documentation

- **[Architecture Overview](architecture.md)** — current application structure and platform layout
- **[Browser Extension](extension.md)** — shared client, runtime contract, popup/background architecture
- **[Team Workflow](workflow.md)** — branch strategy, PR process, CI gates, and contribution policy
- **[Project Roadmap](roadmap.md)** — current status, active architecture work, and next milestones

## Current Product Surface

### Implemented Today
- Textual TUI dashboard and course views
- grades and assignment workflows
- offline-first cache layers
- browser extension popup and background worker
- extension-side shared Canvas client layer
- GitHub Pages documentation site
- CI/CD and protected-branch governance

### Important Repo Policy
- `main` is the canonical long-term branch
- feature branches are temporary and PR-scoped
- merged PR branches should be deleted
- direct AI automation is not part of the merge path

## Deployment

| Environment | URL | Trigger |
|-------------|-----|---------|
| **Docs Site** | [kleinpanic.github.io/CS3704-Canvas-Project](https://kleinpanic.github.io/CS3704-Canvas-Project) | Every push to `main` |
| **Release snapshots** | GitHub Releases | Main/release workflow |

The docs site is built with MkDocs Material and deployed via GitHub Actions.

## CI/CD Snapshot

```text
feature/docs/fix branch
  -> PR to main
  -> Branch Name Policy
  -> Test
  -> Python Compat matrix
  -> maintainer review
  -> squash merge
  -> branch auto-deleted

main
  -> Pages deploy
  -> release/security follow-up workflows
```

## Team

| Role | Member | Responsibility |
|------|--------|----------------|
| **Owner** | Klein Panic | Architecture, CI/CD, releases |
| **Maintainer** | Williammm23 | Feature development |
| **Maintainer** | pjie22 | Documentation and implementation review |
| **Maintainer** | 802797liu | Tests and filtering work |

See [CONTRIBUTORS.md](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/CONTRIBUTORS.md) and [MAINTAINERS.md](https://github.com/kleinpanic/CS3704-Canvas-Project/blob/main/MAINTAINERS.md) for more detail.
