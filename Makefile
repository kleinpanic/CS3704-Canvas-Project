SHELL := bash

APP_NAME = canvas-tui
BIN_DIR  = $(HOME)/.local/bin
VENV_DIR = $(HOME)/.local/venv/$(APP_NAME)
PYTHON   = python3
REQS     = requests textual
SRC      = canvas-tui.py
SHARE_DIR= $(HOME)/.local/share/$(APP_NAME)
APP_PATH = $(SHARE_DIR)/$(APP_NAME).py
REQ_FILE = requirements.txt

.PHONY: all setup install uninstall fmt lint run run-installed update clean

all: install

setup:
	@mkdir -p "$(VENV_DIR)"
	@test -x "$(VENV_DIR)/bin/python" || $(PYTHON) -m venv "$(VENV_DIR)"
	@"$(VENV_DIR)/bin/python" -m pip -q install --upgrade pip
	@if [ -f "$(REQ_FILE)" ]; then \
		"$(VENV_DIR)/bin/pip" -q install -r "$(REQ_FILE)"; \
	else \
		"$(VENV_DIR)/bin/pip" -q install $(REQS); \
	fi

install: setup
	@mkdir -p "$(SHARE_DIR)" "$(BIN_DIR)"
	@install -m 0644 "$(SRC)" "$(APP_PATH)"
	@printf '%s\n' \
		'#!/usr/bin/env bash' \
		'set -euo pipefail' \
		'VENV="$${HOME}/.local/venv/$(APP_NAME)"' \
		'APP="$${HOME}/.local/share/$(APP_NAME)/$(APP_NAME).py"' \
		'exec "$${VENV}/bin/python" "$${APP}" "$$@"' \
		> "$(BIN_DIR)/$(APP_NAME)"
	@chmod 0755 "$(BIN_DIR)/$(APP_NAME)"
	@echo "Installed $(APP_NAME) to $(BIN_DIR)/$(APP_NAME)"

update: install

uninstall:
	@rm -f "$(BIN_DIR)/$(APP_NAME)"
	@rm -rf "$(SHARE_DIR)"
	@echo "NOTE: venv left at $(VENV_DIR) (remove manually if desired)."

fmt: setup
	@"$(VENV_DIR)/bin/python" -m pip -q install ruff black
	@"$(VENV_DIR)/bin/ruff" check --fix "$(SRC)" || true
	@"$(VENV_DIR)/bin/black" "$(SRC)"

lint: setup
	@"$(VENV_DIR)/bin/python" -m pip -q install ruff
	@"$(VENV_DIR)/bin/ruff" check "$(SRC)"

run: setup
	@"$(VENV_DIR)/bin/python" "$(SRC)"

run-installed:
	@"$(BIN_DIR)/$(APP_NAME)"

clean:
	@rm -f "$(BIN_DIR)/$(APP_NAME)"
	@rm -rf "$(SHARE_DIR)"

