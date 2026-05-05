# Testing Patterns

**Analysis Date:** 2026-05-05

## Test Framework

**Runner:**
- pytest — configured in `pyproject.toml`
- Config file: `[tool.pytest]` section in `pyproject.toml`
- Config file: `tests/conftest.py` (shared fixtures)

**Assertion Library:**
- pytest built-in `assert` statements
- `unittest.mock` for mocking (`MagicMock`, `patch`)

**Run Commands:**
```bash
pytest tests/ -q -p no:cacheprovider --tb=short   # Run all tests (CI)
pytest tests/                                     # Run with verbose
pytest tests/test_api.py                          # Single file
pip install -e ".[dev]" && pytest --cov          # With coverage
```

## Test File Organization

**Location:**
- `tests/` directory (separate from source)
- `sdk/canvas_sdk/agent_tools/tests/` — SDK agent tools tests (separate suite)

**Naming:**
- `test_*.py` for all test files
- Class-based: `class TestClassName:` with methods `test_*()`

**Structure:**
```
tests/
├── conftest.py           # Shared fixtures (tmp_dir, sample_config_env, etc.)
├── test_api.py           # CanvasAPI tests
├── test_cache.py         # Cache tests
├── test_config.py        # Config loading tests
├── test_courses.py       # Course-related tests
├── test_grades.py        # Grades tests
└── ...                   # 20+ test files
```

## Test Structure

**Suite Organization:**
```python
class TestClassName:
    def setup_method(self):
        # Per-test setup (not `setup_class`)

    def test_something(self):
        # arrange
        # act
        # assert

    def test_something_else(self):
        # test code
```

**Patterns:**
- `setup_method` for per-test setup (fixtures, mocks)
- `unittest.mock.MagicMock` + `@patch` for mocking
- No `beforeAll` / `afterAll` (per-test isolation preferred)

## Mocking

**Framework:**
- `unittest.mock` (built-in)
- `@patch` decorator for patching imports
- `MagicMock` for creating mock objects

**Patterns:**
```python
from unittest.mock import MagicMock, patch

@patch("canvas_tui.api.requests.Session")
def test_something(mock_session_cls):
    session = MagicMock()
    session.get.return_value = _make_response()
    mock_session_cls.return_value = session
    # test code
```

**What to Mock:**
- `requests.Session` (HTTP layer)
- `canvas_tui.config.Config` (configuration)
- External Canvas API (network calls)

**What NOT to Mock:**
- Internal pure functions (where possible)
- Simple utility functions

## Fixtures

**Defined in `tests/conftest.py`:**
```python
@pytest.fixture
def tmp_dir():
    """Temporary directory for test files."""
    with tempfile.TemporaryDirectory(prefix="canvas_tui_test_") as d:
        yield d

@pytest.fixture
def sample_config_env(monkeypatch, tmp_dir):
    """Set up minimal environment for Config loading."""
    monkeypatch.setenv("CANVAS_TOKEN", "test-token-12345")
    monkeypatch.setenv("CANVAS_BASE_URL", "https://canvas.example.edu")
    # ...
```

## Coverage

**Requirements:**
- Target: ≥80% line coverage (enforced in CI via `fail_under = 80`)
- Exclusions (in `pyproject.toml`):
  - TUI app/screen files (require terminal)
  - Adapter/command/prefetch modules
  - RMP client (integration-dependent)
  - `core/__init__.py`, `models.py`

**Configuration:**
- `pytest-cov` plugin
- `.coveragerc` or `[tool.coverage.run]` in `pyproject.toml`

**View Coverage:**
```bash
pytest --cov=canvas_tui --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Test individual classes/functions in isolation
- Mock all external dependencies (HTTP, config)
- `test_api.py`, `test_cache.py`, `test_config.py`, etc.

**Integration Tests:**
- Not currently explicit (tests for TUI without real Canvas)
- SDK tests in `sdk/canvas_sdk/agent_tools/tests/` (separate)

## Common Patterns

**HTTP Mocking:**
```python
def _make_response(status=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or []
    resp.headers = headers or {}
    resp.raise_for_status.return_value = None
    return resp
```

**Config Mocking:**
```python
cfg = Config(token="test-token", base_url="https://canvas.example.com")
api = CanvasAPI(cfg=cfg)
```

---

*Testing analysis: 2026-05-05*
*Update when test patterns change*