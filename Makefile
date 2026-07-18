SHELL := /bin/bash

PYTHON_BOOTSTRAP ?= python3
VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(PYTHON) -m pip
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help install format lint typecheck test smoke verify clean \
	db-up db-wait db-check db-reset db-down db-logs

help: ## Show available development commands
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Create the virtual environment and install development dependencies
	$(PYTHON_BOOTSTRAP) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install --editable '.[dev]'

format: ## Apply Ruff lint fixes and formatting
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

lint: ## Check lint rules and formatting without changing files
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

typecheck: ## Run strict static type checking
	$(VENV)/bin/mypy

test: ## Run unit tests
	$(VENV)/bin/pytest tests/unit

smoke: ## Verify that the CLI starts and the local environment is supported
	$(PYTHON) -m metadata_pipeline.cli --version
	$(PYTHON) -m metadata_pipeline.cli doctor

verify: lint typecheck test smoke ## Run all local quality gates

db-up: ## Start the ClickHouse demo fixture and wait until it is ready
	$(COMPOSE) up -d clickhouse
	$(MAKE) db-wait

db-wait: ## Wait up to 90 seconds for ClickHouse to accept queries
	./scripts/wait_for_clickhouse.sh

db-check: db-wait ## Validate schema, comments, row counts, and fake-data cases
	RUN_CLICKHOUSE_INTEGRATION=1 $(VENV)/bin/pytest -m integration tests/integration

db-reset: ## Delete the ClickHouse container and volume for a clean initialization
	$(COMPOSE) down --volumes --remove-orphans

db-down: ## Stop ClickHouse while retaining its data volume
	$(COMPOSE) down --remove-orphans

db-logs: ## Show recent ClickHouse logs for troubleshooting
	$(COMPOSE) logs --tail=100 clickhouse

clean: ## Remove local build and test artifacts
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
