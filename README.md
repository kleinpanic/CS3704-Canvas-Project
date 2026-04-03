# CS3704 Canvas Project

A maintainable, team-ready **Canvas LMS productivity client** with a Textual TUI frontend and a documented shared-core architecture for future browser-extension parity.

[![CI](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/ci.yml?branch=main&label=CI)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/kleinpanic/CS3704-Canvas-Project/branch/main/graph/badge.svg)](https://app.codecov.io/gh/kleinpanic/CS3704-Canvas-Project)
[![Security](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/security.yml?branch=main&label=Security)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/security.yml)
[![Pages](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/pages.yml?branch=main&label=Pages)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/pages.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

---

## Overview

This is the **CS3704 team project repository** for a Canvas LMS productivity tool. It combines a working Textual TUI application with architecture documentation, team governance, and automated CI/CD.

### What this project does
- Centralized dashboard for Canvas assignments, announcements, and grades
- Offline-first caching for reliable access
- Calendar integration and ICS export
- Pomodoro timer and notification support
- Course filtering and quick navigation

### Architecture goals
- **Current**: Feature-complete TUI application
- **Shared core**: Reusable domain logic and orchestration
- **Future**: Browser extension parity with same business logic

---

## Architecture

### High-level system design

```mermaid
flowchart TB
  subgraph CLI[CLI Frontend]
    CMD[Command Router]
    TUI[Textual TUI Screens]
    NOTIF[Notifications]
  end

  subgraph EXT[Browser Extension]
    POPUP[Popup UI]
    BG[Background Worker]
    CONTENT[Content Scripts]
  end

  subgraph CORE[Shared Domain Core]
    ORCH[Orchestrators]
    POLICY[Policy Engine]
    NORM[Normalization Layer]
    DIFF[State and Diff Engine]
  end

  subgraph INFRA[Infrastructure Layer]
    API[Canvas API Gateway]
    AUTH[Auth Manager]
    CACHE[SQLite and IndexedDB Cache]
    QUEUE[Event Scheduler]
  end

  CMD --> ORCH
  TUI --> ORCH
  NOTIF --> ORCH
  POPUP --> ORCH
  BG --> ORCH
  CONTENT --> ORCH
  ORCH --> POLICY --> API
  ORCH --> NORM --> CACHE
  ORCH --> DIFF --> CACHE
  ORCH --> QUEUE
  API --> AUTH
```

### Static diagrams
- **[Full Architecture](docs/architecture/complex-architecture.svg)** — component relationships
- **[Sync Flow](docs/architecture/sync-flow.svg)** — data refresh sequence

---

## Quick Start

### Installation

```bash
# Using pipx (recommended)
pipx install .

# Or using pip
pip install .
```

### Configuration

Set your Canvas API token:

```bash
export CANVAS_TOKEN="your_canvas_token_here"
export CANVAS_BASE_URL="https://canvas.vt.edu"  # optional, defaults to VT
```

### Run

```bash
canvas-tui
```

---

## Development

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Testing

```bash
ruff check src tests      # linting
pytest -q                  # run tests
python -m build           # build package
```

---

## Repository Structure

```
.github/                  CI/CD workflows and governance
src/canvas_tui/           Application source code
tests/                    Test suite
docs/architecture/        Mermaid diagrams and SVG exports
docs/assets/              Static images and captures
docs/project/             Planning artifacts and legacy docs
docs-site/                GitHub Pages documentation
```

---

## Team Workflow

### For maintainers
1. Push directly to `main` (protected, but admin bypass enabled)
2. Ensure CI passes before merging others' PRs
3. Review team PRs promptly

### For team members
1. **Never push directly to `main`**
2. Create a feature branch: `feature/your-feature-name`
3. Open a Pull Request
4. Wait for CI to pass and a maintainer to review
5. Merge when approved

### Branch naming convention
- `feature/*` — new features
- `fix/*` — bug fixes
- `chore/*` — maintenance tasks
- `docs/*` — documentation updates

---

## Automation

This repository has extensive automation:

| Workflow | Purpose |
|----------|---------|
| **CI** | Ruff linting, pytest on Python 3.11/3.12/3.13, package build |
| **Security** | CodeQL analysis, dependency review |
| **Pages** | Auto-deploy documentation site |
| **Release** | Create snapshot release on main push |
| **Stale** | Close inactive issues/PRs after 30 days |
| **Labeler** | Auto-label PRs by changed files |

All commits to protected branches must be **GPG signed**.

---

## Documentation

- **[Architecture docs](docs-site/architecture.md)** — system design decisions
- **[Workflow guide](docs-site/workflow.md)** — how the team works
- **[Contributing](CONTRIBUTING.md)** — contribution guidelines
- **[Maintainers](MAINTAINERS.md)** — maintainer responsibilities
- **[Security policy](SECURITY.md)** — security procedures

---

## Course Context

This repository supports **CS3704: Intermediate Software Design and Engineering** project milestones:

- **PM3**: Design documentation, architecture visualization, process evidence
- **PM4+**: Implementation, testing, and delivery

The architecture emphasizes maintainability for a mixed-skill team while protecting the codebase from accidental damage.

---

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
