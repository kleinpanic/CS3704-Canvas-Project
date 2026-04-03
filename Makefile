# CS3704 Canvas TUI - Unified Makefile
# Run `make` or `make help` to see all available commands

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Paths
PYTHON := python3
VENV := .venv
SRC_DIR := src/canvas_tui
TEST_DIR := tests
DOCS_DIR := docs-site
SCRIPTS_DIR := scripts

# Colors for output
CYAN := \033[36m
GREEN := \033[32m
RED := \033[31m
YELLOW := \033[33m
RESET := \033[0m

.PHONY: help setup install dev clean fmt lint test test-all coverage ci docs serve release check

# ============================================================================
# SETUP & INSTALLATION
# ============================================================================

setup: ## Create virtual environment
	@printf "$(CYAN)Setting up virtual environment...$(RESET)\n"
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(VENV)/bin/python -m pip install --upgrade pip -q
	@printf "$(GREEN)✓ Virtual environment ready$(RESET)\n"

install: setup ## Install package
	@printf "$(CYAN)Installing package...$(RESET)\n"
	@$(VENV)/bin/pip install -e . -q
	@printf "$(GREEN)✓ Package installed$(RESET)\n"

dev: setup ## Install with dev dependencies
	@printf "$(CYAN)Installing dev dependencies...$(RESET)\n"
	@$(VENV)/bin/pip install -e ".[dev]" -q
	@$(VENV)/bin/pip install rich pytest-cov pytest-xdist -q
	@printf "$(GREEN)✓ Dev environment ready$(RESET)\n"

# ============================================================================
# CODE QUALITY
# ============================================================================

fmt: dev ## Format code with ruff
	@printf "$(CYAN)Formatting code...$(RESET)\n"
	@$(VENV)/bin/ruff check --fix $(SRC_DIR) $(TEST_DIR) 2>/dev/null || true
	@$(VENV)/bin/ruff format $(SRC_DIR) $(TEST_DIR)
	@printf "$(GREEN)✓ Code formatted$(RESET)\n"

lint: dev ## Run linter
	@printf "$(CYAN)Running linter...$(RESET)\n"
	@$(VENV)/bin/ruff check $(SRC_DIR) $(TEST_DIR)

typecheck: dev ## Run type checker
	@printf "$(CYAN)Running type checker...$(RESET)\n"
	@$(VENV)/bin/mypy $(SRC_DIR) --ignore-missing-imports || true

# ============================================================================
# TESTING
# ============================================================================

test: dev ## Run unit tests
	@printf "$(CYAN)Running tests...$(RESET)\n"
	@$(VENV)/bin/pytest $(TEST_DIR) -v --tb=short

test-q: dev ## Run tests quietly
	@$(VENV)/bin/pytest $(TEST_DIR) -q

test-p: dev ## Run tests in parallel
	@printf "$(CYAN)Running tests in parallel...$(RESET)\n"
	@$(VENV)/bin/pytest $(TEST_DIR) -n auto -q

test-all: dev ## Run full test suite with "sexy" output
	@printf "$(CYAN)Running full test suite...$(RESET)\n"
	@$(VENV)/bin/python $(SCRIPTS_DIR)/run_tests.py

coverage: dev ## Run tests with coverage
	@printf "$(CYAN)Running coverage analysis...$(RESET)\n"
	@$(VENV)/bin/pytest --cov=canvas_tui --cov-report=term-missing --cov-report=html -q
	@printf "$(GREEN)✓ Coverage report: htmlcov/index.html$(RESET)\n"

# ============================================================================
# CI/CD LOCAL SIMULATION
# ============================================================================

ci: dev ## Simulate CI pipeline locally
	@printf "$(CYAN)Simulating CI pipeline...$(RESET)\n"
	@printf "$(YELLOW)→ Lint check$(RESET)\n" && $(VENV)/bin/ruff check $(SRC_DIR) $(TEST_DIR)
	@printf "$(YELLOW)→ Format check$(RESET)\n" && $(VENV)/bin/ruff format --check $(SRC_DIR) $(TEST_DIR)
	@printf "$(YELLOW)→ Tests$(RESET)\n" && $(VENV)/bin/pytest $(TEST_DIR) -q
	@printf "$(YELLOW)→ Build$(RESET)\n" && $(VENV)/bin/python -m build
	@printf "$(GREEN)✓ CI simulation passed$(RESET)\n"

check: fmt lint test ## Format, lint, and test (pre-commit check)
	@printf "$(GREEN)✓ All checks passed$(RESET)\n"

# ============================================================================
# BUILDING & PACKAGING
# ============================================================================

build: dev ## Build package
	@printf "$(CYAN)Building package...$(RESET)\n"
	@$(VENV)/bin/python -m build
	@printf "$(GREEN)✓ Package built: dist/$(RESET)\n"

# ============================================================================
# DOCUMENTATION
# ============================================================================

docs: ## Build documentation
	@printf "$(CYAN)Building documentation...$(RESET)\n"
	@$(VENV)/bin/pip install mkdocs-material -q 2>/dev/null || true
	@cd $(DOCS_DIR) && mkdocs build 2>/dev/null || echo "MkDocs not configured"

serve: ## Serve documentation locally
	@printf "$(CYAN)Serving documentation...$(RESET)\n"
	@cd $(DOCS_DIR) && mkdocs serve

# ============================================================================
# CLEANUP
# ============================================================================

clean: ## Clean build artifacts
	@printf "$(CYAN)Cleaning...$(RESET)\n"
	@rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	@rm -rf $(SRC_DIR)/*.egg-info
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@printf "$(GREEN)✓ Cleaned$(RESET)\n"

clean-all: clean ## Clean everything including venv
	@rm -rf $(VENV)
	@printf "$(GREEN)✓ Fully cleaned$(RESET)\n"

# ============================================================================
# RUNTIME
# ============================================================================

run: dev ## Run the TUI application
	@$(VENV)/bin/python -m canvas_tui

# ============================================================================
# RELEASE
# ============================================================================

release: check build ## Prepare a release (run tests, build)
	@printf "$(GREEN)✓ Ready for release!$(RESET)\n"
	@printf "$(YELLOW)To publish: git tag vX.Y.Z && git push --tags$(RESET)\n"

# ============================================================================
# HELP
# ============================================================================

help: ## Show this help message
	@printf "\n$(CYAN)CS3704 Canvas TUI - Available Commands$(RESET)\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-12s$(RESET) %s\n", $$1, $$2}'
	@printf "\n$(CYAN)Examples:$(RESET)\n"
	@printf "  make dev       - Set up dev environment\n"
	@printf "  make check     - Pre-commit check (fmt+lint+test)\n"
	@printf "  make test-all  - Full test suite with beautiful output\n"
	@printf "  make ci        - Simulate CI pipeline locally\n"
	@printf "  make release   - Prepare a release\n\n"
