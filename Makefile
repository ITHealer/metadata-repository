SHELL := /bin/bash

PYTHON_BOOTSTRAP ?= python3
VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(PYTHON) -m pip
COMPOSE ?= docker compose
SOURCE_REVIEW_COMMIT ?= $(shell git log -1 --format=%H -- metadata/review/commerce_demo)
PUBLISHED_DIR ?= knowledge/published/commerce_demo
CHUNK_OUTPUT ?= build/chunks/commerce_demo.jsonl
INDEX_MANIFEST ?= build/index/manifest.json
INDEX_ACTIONS ?= build/index/actions.json
INDEX_BASE ?= HEAD^
INDEX_HEAD ?= HEAD
SOURCE_COMMIT ?= $(shell git rev-parse HEAD)
RETRIEVAL_REPORT ?= build/index/retrieval-report.json
GENERATOR_MODE ?= mock
LIVE_PUBLISHED_DIR ?= build/live/published/commerce_demo
LIVE_CHUNK_OUTPUT ?= build/live/chunks/commerce_demo.jsonl

.DEFAULT_GOAL := help

.PHONY: help install format lint typecheck test coverage smoke verify clean \
	db-up db-wait db-check db-reset db-down db-logs \
	schema-doc schema-lint schema-diff schema-check \
	review-schema review-draft review-validate review-check \
	publish published-validate chunk-dry-run knowledge-check \
	index-build retrieval-smoke live-uat

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

test: ## Run unit, contract, retrieval, and deterministic E2E tests
	$(VENV)/bin/pytest tests/unit tests/contract tests/retrieval tests/e2e

coverage: ## Enforce 85% coverage for domain, application, and validation core
	$(VENV)/bin/pytest tests/unit tests/contract tests/retrieval tests/e2e \
		--cov=metadata_pipeline.adapters.generator \
		--cov=metadata_pipeline.adapters.index \
		--cov=metadata_pipeline.domain \
		--cov=metadata_pipeline.application \
		--cov=metadata_pipeline.ports.document_generator \
		--cov=metadata_pipeline.ports.index_store \
		--cov=metadata_pipeline.validation \
		--cov-report=term-missing --cov-fail-under=85 $(PYTEST_ARGS)

smoke: ## Verify that the CLI starts and the local environment is supported
	$(PYTHON) -m metadata_pipeline.cli --version
	$(PYTHON) -m metadata_pipeline.cli doctor

verify: lint typecheck coverage smoke review-validate ## Run all local quality gates

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

schema-doc: db-wait ## Generate raw Markdown, Mermaid ER, and schema.json with tbls
	./scripts/extract_schema.sh doc

schema-lint: db-wait ## Require comments for every ClickHouse table and column
	./scripts/extract_schema.sh lint

schema-diff: db-wait ## Compare the live ClickHouse schema with committed raw documentation
	./scripts/extract_schema.sh diff

schema-check: schema-doc schema-lint ## Generate and validate the complete tbls contract
	RUN_TBLS_INTEGRATION=1 $(VENV)/bin/pytest -m schema_integration \
		tests/integration/test_tbls_extraction.py

review-schema: ## Generate JSON Schema from the Pydantic reviewer contract
	./scripts/metadata export-review-schema \
		--output schemas/reviewer_metadata.schema.json

review-draft: ## Create or refresh deterministic reviewer YAML drafts
	./scripts/metadata draft \
		--schema schema/raw/commerce_demo/schema.json \
		--review-dir metadata/review/commerce_demo \
		--contract config/metadata_contract.yml

review-validate: ## Validate reviewer YAML against the raw tbls schema
	./scripts/metadata validate-review \
		--schema schema/raw/commerce_demo/schema.json \
		--review-dir metadata/review/commerce_demo \
		--contract config/metadata_contract.yml

review-check: review-schema review-validate ## Generate and validate the reviewer contract

publish: ## Generate deterministic published Markdown from raw and reviewer metadata
	./scripts/metadata publish \
		--schema schema/raw/commerce_demo/schema.json \
		--review-dir metadata/review/commerce_demo \
		--contract config/metadata_contract.yml \
		--published-dir $(PUBLISHED_DIR) \
		--source-review-commit $(SOURCE_REVIEW_COMMIT) \
		--mode $(GENERATOR_MODE)

published-validate: ## Require committed published Markdown to match validated inputs
	./scripts/metadata validate-published \
		--schema schema/raw/commerce_demo/schema.json \
		--review-dir metadata/review/commerce_demo \
		--contract config/metadata_contract.yml \
		--published-dir $(PUBLISHED_DIR) \
		--source-review-commit $(SOURCE_REVIEW_COMMIT)

chunk-dry-run: ## Build validated semantic chunk JSONL without indexing
	./scripts/metadata chunk \
		--schema schema/raw/commerce_demo/schema.json \
		--review-dir metadata/review/commerce_demo \
		--contract config/metadata_contract.yml \
		--published-dir $(PUBLISHED_DIR) \
		--source-review-commit $(SOURCE_REVIEW_COMMIT) \
		--mode $(GENERATOR_MODE) --dry-run --output $(CHUNK_OUTPUT)

knowledge-check: publish published-validate chunk-dry-run ## Verify publish and chunk contracts

index-build: chunk-dry-run ## Reconcile approved chunks into a deterministic manifest artifact
	./scripts/metadata index-manifest \
		--chunks $(CHUNK_OUTPUT) \
		--manifest $(INDEX_MANIFEST) \
		--source-commit $(SOURCE_COMMIT) \
		--base $(INDEX_BASE) --head $(INDEX_HEAD) \
		--actions-output $(INDEX_ACTIONS)

retrieval-smoke: ## Run 10 golden questions against an approved in-memory fixture
	RETRIEVAL_REPORT=$(RETRIEVAL_REPORT) \
		$(VENV)/bin/pytest tests/retrieval/test_golden_retrieval.py

live-uat: ## Manually call the configured gateway once per document and write isolated artifacts
	./scripts/metadata publish \
		--schema schema/raw/commerce_demo/schema.json \
		--review-dir metadata/review/commerce_demo \
		--contract config/metadata_contract.yml \
		--published-dir $(LIVE_PUBLISHED_DIR) \
		--source-review-commit $(SOURCE_REVIEW_COMMIT) \
		--mode live --chunk-output $(LIVE_CHUNK_OUTPUT)

clean: ## Remove local build and test artifacts
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
