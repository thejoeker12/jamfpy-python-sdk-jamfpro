# Single entrypoint for every dev task; docs only ever point at these targets.

PYTHON_VERSIONS ?= 3.15 3.14 3.13
INTEGRATION_ENV := JAMFPRO_INSTANCE_FQDN JAMFPRO_CLIENT_ID JAMFPRO_CLIENT_SECRET

# .env is optional: CI injects the vars directly, so only pass --env-file when the file exists.
ENV_FILE := $(wildcard .env)
UV_ENV := $(if $(ENV_FILE),--env-file $(ENV_FILE),)

# `make schema-path PATH=/v1/scripts` (and `make scaffold ... PATH=...`) sets make's own PATH, which make then exports to
# every recipe, hiding uv. Keep the value as the schema path and restore the PATH make inherited. GNU make 4.4+ passes the
# command-line PATH to $(shell) as well, so there the inherited one can't be recovered: that case stops with a usage line.
ifeq ($(origin PATH),command line)
SCHEMA_PATH := $(PATH)
override PATH := $(shell /usr/bin/printenv PATH)
ifeq ($(PATH),$(SCHEMA_PATH))
$(error this make can't restore PATH after PATH=$(SCHEMA_PATH); pass SCHEMA_PATH=<path> instead of PATH=<path>)
endif
endif

.DEFAULT_GOAL := help
.PHONY: help setup lock lint typecheck test coverage test-integration check check-matrix schemas schema-paths schema-path scaffold coverage-doc coverage-doc-check

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create or refresh .venv from uv.lock
	uv sync

lock: ## Re-resolve uv.lock after a dependency change in pyproject.toml (commit both)
	uv lock

lint: ## Run pylint over every tracked Python file (fails under 9.0)
	uv run pylint $$(git ls-files '*.py') --fail-under=9.0

typecheck: ## Run mypy (strict, from pyproject.toml) over the package, tools/ and examples/
	uv run mypy jamfpy tools examples

test: ## Run the offline unit suite
	uv run pytest -q

coverage: ## Run the unit suite with branch coverage (fails under 90%)
	uv run pytest -q --cov=jamfpy --cov-branch --cov-fail-under=90

test-integration: ## Run the live suite against a real tenant (reads .env when present)
	@uv run $(UV_ENV) python -c 'import os, sys; m = [k for k in sys.argv[1:] if not os.environ.get(k)]; sys.exit("test-integration: missing or empty env vars: " + ", ".join(m) + " (set them, or copy .env.example to .env)" if m else 0)' $(INTEGRATION_ENV)
	uv run $(UV_ENV) pytest -m integration tests/integration -v

check: lint typecheck coverage coverage-doc-check ## Run every gate CI runs

check-matrix: ## Run check once per interpreter in PYTHON_VERSIONS, each in its own .venv-<version>
	@for v in $(PYTHON_VERSIONS); do \
		echo "==> Python $$v"; \
		UV_PYTHON=$$v UV_PROJECT_ENVIRONMENT=.venv-$$v $(MAKE) check || exit 1; \
	done

schemas: ## Pull both API schemas and re-probe pro-supplement.json (tenant from .env), writing all three only if every step succeeds
	uv run $(UV_ENV) python -m tools.schemas refresh

schema-paths: ## List schema paths and their verbs: make schema-paths API=pro MATCH=scripts (MATCH optional)
	@test -n "$(API)" || { echo "usage: make schema-paths API=<pro|classic> [MATCH=<text>]" >&2; exit 2; }
	@uv run python -m tools.schemas paths --api '$(API)' $(if $(MATCH),--match '$(MATCH)')

schema-path: ## Show one path's methods, params and resolved request body: make schema-path API=pro PATH=/v1/scripts
	@test -n "$(API)" -a -n "$(SCHEMA_PATH)" || { echo "usage: make schema-path API=<pro|classic> PATH=<path>" >&2; exit 2; }
	@uv run python -m tools.schemas path --api '$(API)' '$(SCHEMA_PATH)'

scaffold: ## Generate an endpoint, its wiring, tests and live spec from the schema: make scaffold API=pro PATH=/v1/things [NAME=Things] [DRY_RUN=1]
	@test -n "$(API)" -a -n "$(SCHEMA_PATH)" || { echo "usage: make scaffold API=<pro|classic> PATH=<path> [NAME=<ClassName>] [DRY_RUN=1]" >&2; exit 2; }
	@uv run python -m tools.scaffold --api '$(API)' --path '$(SCHEMA_PATH)' $(if $(NAME),--name '$(NAME)') $(if $(DRY_RUN),--dry-run)

coverage-doc: ## Regenerate COVERAGE.md from the wired endpoints, the schemas and the live specs (never hand-edit it)
	uv run python -m tools.coverage_doc

coverage-doc-check: ## Fail with a diff when COVERAGE.md differs from what make coverage-doc would write
	uv run python -m tools.coverage_doc --check
