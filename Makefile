# Single entrypoint for every dev task; docs only ever point at these targets.

PYTHON_VERSIONS ?= 3.15 3.14 3.13
INTEGRATION_ENV := JAMFPRO_INSTANCE_FQDN JAMFPRO_CLIENT_ID JAMFPRO_CLIENT_SECRET

# .env is optional: CI injects the vars directly, so only pass --env-file when the file exists.
ENV_FILE := $(wildcard .env)
UV_ENV := $(if $(ENV_FILE),--env-file $(ENV_FILE),)

.DEFAULT_GOAL := help
.PHONY: help setup lint typecheck test coverage test-integration check check-matrix

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create or refresh .venv from uv.lock
	uv sync

lint: ## Run pylint over every tracked Python file (fails under 9.0)
	uv run pylint $$(git ls-files '*.py') --fail-under=9.0

typecheck: ## Run mypy (strict, from pyproject.toml) over the package
	uv run mypy jamfpy

test: ## Run the offline unit suite
	uv run pytest -q

coverage: ## Run the unit suite with branch coverage (fails under 90%)
	uv run pytest -q --cov=jamfpy --cov-branch --cov-fail-under=90

test-integration: ## Run the live suite against a real tenant (reads .env when present)
	@uv run $(UV_ENV) python -c 'import os, sys; m = [k for k in sys.argv[1:] if not os.environ.get(k)]; sys.exit("test-integration: missing or empty env vars: " + ", ".join(m) + " (set them, or copy .env.example to .env)" if m else 0)' $(INTEGRATION_ENV)
	uv run $(UV_ENV) pytest -m integration tests/integration -v

check: lint typecheck coverage ## Run every gate CI runs

check-matrix: ## Run check once per interpreter in PYTHON_VERSIONS, each in its own .venv-<version>
	@for v in $(PYTHON_VERSIONS); do \
		echo "==> Python $$v"; \
		UV_PYTHON=$$v UV_PROJECT_ENVIRONMENT=.venv-$$v $(MAKE) check || exit 1; \
	done
