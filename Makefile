# ==========================================================
# AI-Telegram-News-Bot — Developer Task Runner
# ----------------------------------------------------------
# Thin, discoverable wrappers around the project's quality
# gates and run commands. Every target is also what CI runs,
# so "green locally" means "green in CI".
#
#   make install    install the package + dev tooling (editable)
#   make lint       ruff lint checks
#   make format     black + ruff --fix (auto-format & fix imports)
#   make typecheck  mypy static type checking (strict, src/ only)
#   make test       pytest unit + integration suite
#   make check      lint + typecheck + test (the full gate)
#   make run        run the bot CLI (ARGS="all" to pass a command)
#   make clean      remove caches and build artifacts
# ==========================================================

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip
ARGS   ?=

.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test check run clean

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package with dev extras (editable).
	$(PIP) install -e ".[dev]"

lint:  ## Run ruff lint checks.
	$(PYTHON) -m ruff check src tests

format:  ## Auto-format with black and fix imports/lints with ruff.
	$(PYTHON) -m black src tests
	$(PYTHON) -m ruff check --fix src tests

typecheck:  ## Run mypy static type checking (strict, src/ only).
	$(PYTHON) -m mypy

test:  ## Run the test suite.
	$(PYTHON) -m pytest

check: lint typecheck test  ## Run the full quality gate (lint + typecheck + test).

run:  ## Run the bot CLI. Pass a command via ARGS, e.g. `make run ARGS=all`.
	$(PYTHON) -m newsbot $(ARGS)

clean:  ## Remove caches and build artifacts.
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
