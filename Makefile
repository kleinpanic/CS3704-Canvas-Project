SHELL := bash

APP_NAME = canvas-tui
BIN_DIR  = $(HOME)/.local/bin
VENV_DIR = $(HOME)/.local/venv/$(APP_NAME)
PYTHON   = python3
SRC_DIR  = src/canvas_tui
REQ_FILE = requirements.txt

.PHONY: all setup install uninstall fmt lint run test clean dev

all: install

setup:
	@mkdir -p "$(VENV_DIR)"
	@test -x "$(VENV_DIR)/bin/python" || $(PYTHON) -m venv "$(VENV_DIR)"
	@"$(VENV_DIR)/bin/python" -m pip -q install --upgrade pip
	@"$(VENV_DIR)/bin/pip" -q install -r "$(REQ_FILE)"

install: setup
	@"$(VENV_DIR)/bin/pip" -q install -e .
	@mkdir -p "$(BIN_DIR)"
	@printf '%s\n' \
		'#!/usr/bin/env bash' \
		'set -euo pipefail' \
		'VENV="$${HOME}/.local/venv/$(APP_NAME)"' \
		'exec "$${VENV}/bin/python" -m canvas_tui.app "$$@"' \
		> "$(BIN_DIR)/$(APP_NAME)"
	@chmod 0755 "$(BIN_DIR)/$(APP_NAME)"
	@echo "Installed $(APP_NAME) to $(BIN_DIR)/$(APP_NAME)"

dev: setup
	@"$(VENV_DIR)/bin/pip" -q install -e ".[dev]"

update: install

uninstall:
	@rm -f "$(BIN_DIR)/$(APP_NAME)"
	@echo "Uninstalled $(APP_NAME)"

fmt: dev
	@"$(VENV_DIR)/bin/ruff" check --fix $(SRC_DIR) || true
	@"$(VENV_DIR)/bin/ruff" format $(SRC_DIR)

lint: dev
	@"$(VENV_DIR)/bin/ruff" check $(SRC_DIR)

test: dev
	@"$(VENV_DIR)/bin/pytest" tests/ -v --tb=short

run: setup
	@"$(VENV_DIR)/bin/python" -m canvas_tui.app

run-installed:
	@"$(BIN_DIR)/$(APP_NAME)"

clean:
	@rm -f "$(BIN_DIR)/$(APP_NAME)"
	@rm -rf build/ dist/ *.egg-info src/*.egg-info
