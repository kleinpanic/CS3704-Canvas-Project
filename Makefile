# CS3704 Canvas Calendar Agent - Unified Makefile
# Run `make` or `make help` to see all available commands

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Paths
PYTHON := python3
VENV := .venv
SRC_DIR := src/canvas_tui
SDK_DIR := src/sdk
EXT_DIR := extension
TEST_DIR := tests
DOCS_DIR := docs-site
SCRIPTS_DIR := scripts

# HuggingFace artifacts (v3.0 v7-dpo release)
HF_USER := kleinpanic93
HF_MODEL := $(HF_USER)/canvas-calendar-agent-v7-dpo
HF_DATASET := $(HF_USER)/canvas-calendar-preferences-v7
HF_SPACE := $(HF_USER)/canvas-calendar-agent-demo

LIVE_DEMO := https://kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/
HF_SPACE_URL := https://huggingface.co/spaces/$(HF_SPACE)
HF_MODEL_URL := https://huggingface.co/$(HF_MODEL)
HF_DATASET_URL := https://huggingface.co/datasets/$(HF_DATASET)

# Colors for output
CYAN := \033[36m
GREEN := \033[32m
RED := \033[31m
YELLOW := \033[33m
RESET := \033[0m

.PHONY: help setup install install-sdk install-extension install-all dev clean fmt lint test test-all coverage ci docs serve release check demo demo-local demo-open hf-info

# ============================================================================
# SETUP & INSTALLATION
# ============================================================================

setup: ## Create virtual environment
	@printf "$(CYAN)Setting up virtual environment...$(RESET)\n"
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(VENV)/bin/python -m pip install --upgrade pip -q
	@printf "$(GREEN)✓ Virtual environment ready$(RESET)\n"

install: setup ## Install TUI package
	@printf "$(CYAN)Installing TUI package...$(RESET)\n"
	@$(VENV)/bin/pip install -e . -q
	@printf "$(GREEN)✓ TUI installed$(RESET)\n"

install-sdk: setup ## Install agentic SDK with HF auto-download
	@printf "$(CYAN)Installing canvas_sdk with auto-download support...$(RESET)\n"
	@$(VENV)/bin/pip install -e "$(SDK_DIR)[autodownload]" -q
	@printf "$(GREEN)✓ SDK installed — first agent run pulls$(RESET) $(YELLOW)$(HF_MODEL)$(RESET) $(GREEN)from HF$(RESET)\n"

install-extension: ## Install Chrome extension dependencies
	@printf "$(CYAN)Installing extension deps...$(RESET)\n"
	@cd $(EXT_DIR) && npm install --silent
	@printf "$(GREEN)✓ Extension deps installed$(RESET)\n"
	@printf "$(YELLOW)→ chrome://extensions (developer mode) → Load unpacked → select $(EXT_DIR)/src/$(RESET)\n"

install-all: install install-sdk install-extension ## One-shot: TUI + SDK + extension
	@printf "$(GREEN)✓ Full stack installed (TUI + SDK + extension)$(RESET)\n"
	@$(MAKE) -s hf-info

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

test-all: dev ## Run full test suite with sexy output
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
	@bash tools/clean.sh
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
# AGENT DEMO (Gemma-4-E2B-IT DPO model)
# ============================================================================

demo: ## Open the live HF Space demo in browser
	@printf "$(CYAN)Opening live demo: $(LIVE_DEMO)$(RESET)\n"
	@xdg-open "$(LIVE_DEMO)" 2>/dev/null || open "$(LIVE_DEMO)" 2>/dev/null || printf "$(YELLOW)Open manually: $(LIVE_DEMO)$(RESET)\n"

demo-local: install-sdk ## Run agent locally (auto-downloads DPO model on first use)
	@printf "$(CYAN)Running agent with $(HF_MODEL)...$(RESET)\n"
	@$(VENV)/bin/python -c "from canvas_sdk import CanvasAgent; a = CanvasAgent.auto(); print(a.run('Plan my finals study schedule.'))"

demo-open: ## Open the HuggingFace Space directly
	@printf "$(CYAN)Opening HF Space: $(HF_SPACE_URL)$(RESET)\n"
	@xdg-open "$(HF_SPACE_URL)" 2>/dev/null || open "$(HF_SPACE_URL)" 2>/dev/null || printf "$(YELLOW)Open manually: $(HF_SPACE_URL)$(RESET)\n"

hf-info: ## Show HuggingFace links (model / dataset / space)
	@printf "\n$(CYAN)🤗 HuggingFace artifacts$(RESET)\n"
	@printf "  $(YELLOW)Model:  $(RESET)$(HF_MODEL_URL)\n"
	@printf "  $(YELLOW)Dataset:$(RESET) $(HF_DATASET_URL)\n"
	@printf "  $(YELLOW)Space:  $(RESET)$(HF_SPACE_URL)\n"
	@printf "  $(YELLOW)Live:   $(RESET)$(LIVE_DEMO)\n\n"

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
	@printf "\n$(CYAN)CS3704 Canvas Calendar Agent — Commands$(RESET)\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-18s$(RESET) %s\n", $$1, $$2}'
	@printf "\n$(CYAN)Quick start$(RESET)\n"
	@printf "  $(YELLOW)make install-all$(RESET)   - One-shot: TUI + SDK + extension\n"
	@printf "  $(YELLOW)make demo$(RESET)          - Open live demo (Gemma-4-E2B-IT DPO via HF Space)\n"
	@printf "  $(YELLOW)make demo-local$(RESET)    - Run agent locally (auto-downloads DPO model)\n"
	@printf "  $(YELLOW)make hf-info$(RESET)       - Show HuggingFace artifact URLs\n"
	@printf "\n$(CYAN)🤗 Live HuggingFace artifacts$(RESET)\n"
	@printf "  $(YELLOW)Model:  $(RESET)$(HF_MODEL_URL)\n"
	@printf "  $(YELLOW)Dataset:$(RESET) $(HF_DATASET_URL)\n"
	@printf "  $(YELLOW)Space:  $(RESET)$(HF_SPACE_URL)\n"
	@printf "  $(YELLOW)Demo:   $(RESET)$(LIVE_DEMO)\n\n"
