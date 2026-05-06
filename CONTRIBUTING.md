# Contributing to CS3704 Canvas Project

This document covers everything a developer or team member needs to work on this project.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Git with GPG signing configured
- Node.js (for extension work)

### Install

```bash
git clone https://github.com/kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run the TUI locally

```bash
export CANVAS_TOKEN="your_canvas_token_here"
export CANVAS_BASE_URL="https://canvas.vt.edu"
canvas-tui
```

### Run tests and linting

```bash
ruff check src tests      # linting
ruff format --check src tests  # format check
mypy src                  # type checking
pytest -q                 # run tests
python -m build           # build package
```

---

## Repository Structure

```
.github/                  CI/CD workflows and governance
extension/                Browser extension source (presentation only)
src/canvas_tui/           TUI application source code
  agent/                  v2 CalendarAgent (tool calls + study planning)
src/sdk/canvas_sdk/       Python SDK — single source of agent logic
hf-space/                 HuggingFace Space (Gradio app loading v7-dpo)
tests/                    Test suite
scripts/                  Data contribution utilities (see scripts/README.md)
docs/                     Architecture and research docs
docs-site/                GitHub Pages documentation + browser demo
data/
  trajectories/           v2 SFT training data
    collab/               Teammate-contributed trajectory JSONL files
    seeds/                Canonical seed examples
  v1-reranker/            Legacy v1 preference pair data
```

---

## Team Workflow

### For maintainers

1. Treat `main` as the only long-term branch
2. Use short-lived feature branches for scoped work
3. Ensure CI passes before merging others' PRs
4. Prefer squash merges and let GitHub auto-delete merged branches

### For team members

1. **Never push directly to `main`**
2. Create a short-lived branch using one of the prefixes below
3. Open a Pull Request into `main`
4. Wait for CI to pass and a maintainer to review
5. Merge with squash when approved

---

## Branch Naming Convention

All branches must match `<prefix>/<slug>` where slug is lowercase letters, digits, dots, and hyphens.

| Prefix | Use for |
|--------|---------|
| `feature/*` | New features |
| `feat/*` | New features (short form) |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation updates |
| `chore/*` | Maintenance and tooling |
| `refactor/*` | Code refactoring without behavior change |
| `test/*` | Test additions or fixes |
| `hotfix/*` | Urgent production fixes |
| `dependabot/*` | Automated dependency updates |

---

## Commit Conventions

This project uses **Conventional Commits**. All commit messages must follow:

```
<type>(<scope>): <description>
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `style`, `ci`, `build`, `revert`

Examples:
- `feat(sdk): add calendar adapter migration`
- `fix(hf-space): guard empty-send path`
- `docs(readme): add distribution table`

PRs with non-conventional titles will be rejected by the `pr-quality` CI check.

## Commit Signing

Protected branch rules require signed commits on `main`. Sign local commits with GPG or SSH signing keys.

---

## PR Expectations

- Use a conventional commit title (enforced by CI)
- Update CHANGELOG.md under the current version's `Added`/`Changed`/`Fixed` section
- Keep PRs focused — one concern per PR
- PRs > 1000 lines of diff require the `large-pr` label
- Link an issue when one exists
- Include screenshots or evidence for UI/docs changes
- No secrets, tokens, or PII

---

## Automation

| Workflow | Purpose |
|----------|---------|
| **CI** | Ruff linting, pytest on Python 3.11/3.12/3.13, package build |
| **Security** | CodeQL analysis, dependency review |
| **Pages** | Auto-deploy documentation site |
| **Release** | Create snapshot release on main push; stable release on `v*` tag |
| **Stale** | Close inactive issues/PRs after 30 days |
| **Labeler** | Auto-label PRs by changed files |
| **PR Quality** | Enforce conventional title, CHANGELOG entry, PR size |
| **Version Check** | Fail PRs where pyproject.toml versions drift or CHANGELOG entry missing |
| **Nightly** | Daily pre-release build tagged `nightly-YYYYMMDD-<sha>` |

The repository is configured for squash-only merges into protected `main`, linear history, and branch auto-delete after merge. All commits to protected branches must be **GPG signed**.

---

## Course Context

This repository supports **CS3704: Intermediate Software Design and Engineering** project milestones:

- **PM3**: Design documentation, architecture visualization, process evidence
- **PM4+**: Implementation, testing, and delivery

The architecture emphasizes maintainability for a mixed-skill team while protecting the codebase from accidental damage.

---

## Local Quality Checks

```bash
ruff check src tests
pytest tests -q
```

Run these before opening a PR. CI will catch failures, but catching them locally is faster.
