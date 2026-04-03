# Team Onboarding Guide

Welcome to the CS3704 Canvas Project team! This guide will get you up and running quickly.

## Quick Start (5 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project

# 2. Set up development environment
make dev

# 3. Run tests to verify setup
make test

# 4. Run the TUI
make run
```

## Repository Overview

| Directory | Purpose |
|-----------|---------|
| `src/canvas_tui/` | Main application source code |
| `tests/` | Unit test suite |
| `docs/architecture/` | Design documents and diagrams |
| `docs-site/` | GitHub Pages documentation |
| `.github/` | CI/CD workflows and templates |

## Development Workflow

### 1. Find Work
- Check the [Project Board](https://github.com/users/kleinpanic/projects/5)
- Browse [Open Issues](https://github.com/kleinpanic/CS3704-Canvas-Project/issues)
- Comment to claim an issue

### 2. Create Branch
```bash
git checkout main
git pull
git checkout -b feature/your-feature-name
```

Branch naming:
- `feature/*` — new features
- `fix/*` — bug fixes
- `chore/*` — maintenance
- `docs/*` — documentation

### 3. Make Changes
- Write clean, tested code
- Follow existing patterns
- Run `make check` before committing

### 4. Open Pull Request
```bash
git push origin feature/your-feature-name
```
Then open a PR on GitHub. Fill in the template.

### 5. Get Reviewed
- CI must pass (lint + tests)
- Wait for maintainer approval
- Address any feedback

### 6. Merge
A maintainer will merge when approved.

## Key Commands

| Command | Purpose |
|---------|---------|
| `make dev` | Set up development environment |
| `make check` | Pre-commit check (fmt + lint + test) |
| `make test` | Run unit tests |
| `make test-all` | Full test suite with "sexy" output |
| `make coverage` | Run tests with coverage report |
| `make ci` | Simulate CI pipeline locally |
| `make run` | Run the TUI application |

## Code Style

- **Formatter**: Ruff (Black-compatible, 88 char line length)
- **Imports**: Automatic sorting (isort)
- **Type hints**: Encouraged (checked by mypy)
- **Tests**: pytest, aim for >80% coverage

Run `make fmt` to auto-format before committing.

## Project Structure

```
src/canvas_tui/
├── api.py          # Canvas API client
├── app.py          # Textual application
├── cache.py        # SQLite persistence
├── cli.py          # Command-line interface
├── config.py       # Configuration
├── models.py       # Data models
├── state.py        # Application state
├── screens/        # TUI screens
│   ├── dashboard.py
│   ├── courses.py
│   └── ...
└── widgets/        # Reusable components
```

## Communication

- **Questions**: [GitHub Discussions](https://github.com/kleinpanic/CS3704-Canvas-Project/discussions)
- **Bugs/Features**: [GitHub Issues](https://github.com/kleinpanic/CS3704-Canvas-Project/issues)
- **Urgent**: Contact @kleinpanic

## Configuration

### Canvas API Token

1. Log into Canvas (Virginia Tech)
2. Go to Account → Settings → Approved Integrations
3. Generate a new token
4. Set environment variable:

```bash
export CANVAS_TOKEN="your_token_here"
export CANVAS_BASE_URL="https://canvas.vt.edu"  # optional
```

Or create `.env` file:
```
CANVAS_TOKEN=your_token_here
CANVAS_BASE_URL=https://canvas.vt.edu
```

## Testing

Run tests:
```bash
make test        # Quick unit tests
make test-all    # Full suite with beautiful output
make coverage    # Coverage report
```

Write tests in `tests/`:
```python
# tests/test_feature.py
def test_feature_works():
    result = my_function()
    assert result == expected_value
```

## Common Issues

### "Module not found: textual"
```bash
make dev  # reinstall dependencies
```

### Tests failing after pull
```bash
make clean
make dev
make test
```

### Can't push to main
You need maintainer permissions. Open a PR instead.

## Architecture Overview

The project follows **Model-View-Controller**:

- **Model**: Canvas API interactions, state management (`api.py`, `state.py`, `models.py`)
- **View**: Textual screens and widgets (`screens/`, `widgets/`)
- **Controller**: Application orchestration (`app.py`, `cli.py`)

Key patterns:
- **Command Pattern**: User actions are encapsulated as commands
- **Repository Pattern**: Data access abstracted through API gateway
- **Offline-first**: SQLite cache for reliable offline operation

## Next Steps

1. Read the [Architecture docs](https://kleinpanic.github.io/CS3704-Canvas-Project/architecture.html)
2. Browse the [Wiki](https://github.com/kleinpanic/CS3704-Canvas-Project/wiki)
3. Pick an issue from the [Project Board](https://github.com/users/kleinpanic/projects/5)
4. Ask questions in [Discussions](https://github.com/kleinpanic/CS3704-Canvas-Project/discussions)

## Getting Help

- Check this guide and the wiki first
- Search existing issues/discussions
- Ask in discussions if not covered
- Contact @kleinpanic for urgent issues

Welcome to the team! 🎉
