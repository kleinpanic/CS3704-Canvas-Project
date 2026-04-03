# CS3704 Canvas Project

A maintainable, team-ready **Canvas LMS productivity client** built around a Textual TUI today and a documented shared-core architecture for future browser-extension parity.

This repository is the cleaned-up **CS3704** project home for the team deliverables, source code, architecture artifacts, governance rules, and release automation.

[![CI](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/ci.yml?branch=main&label=CI)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/ci.yml)
[![Security](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/security.yml?branch=main&label=Security)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/security.yml)
[![Pages](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/pages.yml?branch=main&label=Pages)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/pages.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

## Why this repo exists

The project started from the earlier `CanvasTui-Proposal` work and was promoted into a course repo with:
- stronger project governance
- documentation and architecture assets for PM3+
- maintainable team workflows for a 4-person group
- CI/CD, security checks, and protected-branch discipline

## Core product direction

- **Current frontend:** Textual-based TUI for Canvas
- **Shared-core goal:** reusable orchestration, normalization, policy, and caching concepts
- **Future parity target:** browser extension can reuse the same domain logic and workflows conceptually

## Key features

- planner / assignment dashboard
- announcements and syllabus browsing
- grades overview and trend widgets
- file browsing + download workflows
- calendar / ICS export
- offline cache support
- pomodoro + notifications
- structured filtering and course views

## Repository layout

```text
.github/                  GitHub governance and workflow automation
src/canvas_tui/           application source
tests/                    automated tests
docs/architecture/        Mermaid + SVG architecture artifacts
docs/assets/architecture/ exported figures and captures
docs/project/             planning / migration / legacy project docs
docs-site/                GitHub Pages documentation source
```

## Architecture snapshot

### Static diagram
![Complex Architecture](docs/architecture/complex-architecture.svg)

### Sync flow
![Sync Flow](docs/architecture/sync-flow.svg)

### Mermaid overview
```mermaid
flowchart TB
  subgraph CLI[CLI Frontend]
    CLI_CMD[Command Router - argparse-typer]
    CLI_TUI[Textual TUI Screens]
    CLI_NOTIF[Notification Adapter]
  end

  subgraph EXT[Browser Extension Frontend]
    EXT_POPUP[Popup UI]
    EXT_BG[Background Service Worker]
    EXT_CONTENT[Content Script Bridge]
  end

  subgraph CORE[Shared Domain Core]
    ORCH[Use Cases / Orchestrators]
    POLICY[Policy Engine]
    NORM[Normalization + Mapping]
    DIFF[State + Diff Engine]
  end

  subgraph INFRA[Infrastructure + Integration]
    API[Canvas API Gateway]
    AUTH[Auth + Session Manager]
    CACHE[Persistence + Cache<br/>SQLite / IndexedDB]
    QUEUE[Event Queue + Scheduler]
    OBS[Observability + Metrics]
  end

  CLI_CMD --> ORCH
  CLI_TUI --> ORCH
  CLI_NOTIF --> ORCH
  EXT_POPUP --> ORCH
  EXT_BG --> ORCH
  EXT_CONTENT --> ORCH
  ORCH --> POLICY --> API
  ORCH --> NORM --> CACHE
  ORCH --> DIFF --> CACHE
  ORCH --> QUEUE
  API --> AUTH
  OBS -. traces .-> ORCH
```

## Install

### pipx
```bash
pipx install .
```

### pip
```bash
pip install .
```

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -q
python -m build
```

## Configuration

Set a Canvas token and optional base URL:

```bash
export CANVAS_TOKEN="your_token_here"
export CANVAS_BASE_URL="https://canvas.vt.edu"
```

## Maintainer workflow

1. Open or pick an Issue
2. Branch from `main`
3. Open a PR
4. Pass CI/security checks
5. Get review
6. Merge through GitHub

See also:
- `CONTRIBUTING.md`
- `MAINTAINERS.md`
- `SECURITY.md`
- `docs-site/`

## Automation in this repo

- PR-only protected `main`
- required signed commits on protected branch
- CI: lint + tests + package build
- security: CodeQL + dependency review
- dependabot updates
- stale issue / PR handling
- PR auto-labeling by changed paths
- GitHub Pages docs portal
- automatic snapshot package release on clean `main` pushes

## Course context

This repo supports the **CS3704** project milestones. PM3 specifically emphasizes:
- high-level design
- low-level design + pattern reasoning
- design sketch / architecture visualization
- process evidence (Scrum review + planning)

## License

GPL-3.0-or-later. See `LICENSE`.
