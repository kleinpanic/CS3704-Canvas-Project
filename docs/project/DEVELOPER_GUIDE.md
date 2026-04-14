# CS3704 Canvas TUI — Developer Guide

## Overview

Canvas TUI is a Textual-based terminal client for Canvas LMS. This guide covers everything you need to get running, test, and release.

---

## Quick Start

```bash
git clone git@github.com:kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project
make install-dev
make test
make run
```

---

## Environment Setup

### Requirements
- Python 3.11 or higher
- Git
- A Canvas LMS account (VT or equivalent)

### `make install-dev`
Installs the package in editable mode with all dev dependencies AND sets up pre-commit hooks.
```bash
make install-dev
```

What it runs:
1. Creates `.venv/` if not present
2. Installs package: `pip install -e ".[dev]"`
3. Installs pre-commit hooks (ruff, etc.)

### Dev vs Prod Build

| Command | Use Case |
|---------|----------|
| `pip install .` | Prod / frozen install |
| `pip install -e ".[dev]"` | Dev with editable source |
| `make install-dev` | Same as above + pre-commit setup |

---

## Core Make Targets

| Target | What it does |
|--------|-------------|
| `make test` | Run pytest quietly (`-q`) |
| `make build` | Run `python -m build` → produces `dist/` |
| `make typecheck` | Run mypy (advisory only — warnings, not blockers) |
| `make ci` | Local CI simulation: lint + format check + tests + build |
| `make check` | Pre-commit: format + lint + test |

---

## Running Tests

```bash
make test        # quiet output
make test-p      # parallel execution
make test-all    # full suite with Rich output
make coverage    # coverage report → htmlcov/index.html
```

All tests live in `tests/`. New modules must have a matching `tests/test_<module>.py`.

### Writing Tests
- Use `pytest` framework
- One file per module: `tests/test_<module>.py`
- Each class covers one module/component
- Use `setup_method` / `teardown_method` for clean state

---

## Code Quality

```bash
make fmt        # auto-format with ruff
make lint       # ruff check (no fixes)
make typecheck  # mypy type check (advisory)
```

**Linting policy:** Only syntax errors (E), undefined names (F), and import errors block a PR. Style is advisory — the formatter handles it.

---

## Building for Release

```bash
make build        # produces dist/ with wheel + tarball
make release      # runs: check + build + tag instructions
```

Tag and publish:
```bash
git tag v1.x.x
git push --tags
```

---

## Making a Contribution

1. Pick or open an Issue
2. Create a branch: `feature/<name>`, `fix/<name>`, `docs/<name>`, `test/<name>`
3. Write code + tests
4. Run `make check` before pushing
5. Open a PR → CI runs lint + tests
6. If CI fails, AI fixup branch may be pushed to help — review and merge

---

## Architecture Overview

```
src/canvas_tui/
├── app.py          # Textual App entry point
├── cache.py        # Disk-backed response cache (TTL + stale-while-offline)
├── config.py       # Configuration loading
├── filtering.py    # Query/filter parsing
├── models.py       # Data models
├── normalize.py    # API normalization
├── utils.py        # Shared utilities (strip_html, rel_time, etc.)
├── widgets/        # Textual widget components
│   ├── command_bar.py
│   ├── pomodoro.py
│   ├── plots.py
│   └── charts.py
└── screens/        # App screens
    ├── dashboard.py
    ├── grades.py
    ├── courses.py
    ├── weekview.py
    └── ...
```

---

## Documentation

- `docs-site/` — MkDocs site (published to GitHub Pages on main push)
- `docs/architecture/` — Architecture decision records
- `docs/project/` — Planning artifacts (read-only)
- `SECURITY.md` — Security policy
- `CONTRIBUTING.md` — Workflow rules

---

## Common Issues

**Import errors after pull:** Run `make install-dev` again — your venv may be stale.

**Tests fail after installing:** Make sure you're using the venv's pytest: `make test` handles this automatically.

**Type checker warnings:** These are advisory — they do not block CI or PRs.

---

_Questions? Open an issue on GitHub or ask in the team channel._