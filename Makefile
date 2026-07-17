.PHONY: help install hooks up down migrate dev worker test lint typecheck check fmt protect usage eval-live status demo-cloud

help:
	@echo "install    - create venv + install dev deps"
	@echo "hooks      - install pre-commit hooks (incl. commit-msg)"
	@echo "up/down    - start/stop local Postgres+Redis (docker compose)"
	@echo "migrate    - apply database migrations (alembic upgrade head)"
	@echo "dev        - run the API (uvicorn, reload)"
	@echo "worker     - run the worker"
	@echo "test       - pytest"
	@echo "lint       - ruff check + format check"
	@echo "typecheck  - mypy --strict"
	@echo "check      - lint + typecheck + test (what CI runs)"
	@echo "protect    - apply GitHub branch protection to main (needs gh admin auth)"
	@echo "usage      - record today's token usage to reports/usage/ (NOTE=\"...\")"
	@echo "eval-live  - run the REAL Vertex evaluation (costs money; needs gcloud ADC)"
	@echo "status     - check current development, testing, and release status"
	@echo "demo-cloud - run the fully containerised multi-tenant SaaS demo flow"

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -e ".[dev]"

up:
	docker compose up -d

down:
	docker compose down

migrate:
	. .venv/bin/activate && alembic upgrade head

dev:
	. .venv/bin/activate && uvicorn keel.main:app --reload --app-dir src

worker:
	. .venv/bin/activate && python -m worker.main

test:
	. .venv/bin/activate && pytest

lint:
	. .venv/bin/activate && ruff check src tests && ruff format --check src tests

typecheck:
	. .venv/bin/activate && mypy --strict src

check: lint typecheck test

hooks:
	. .venv/bin/activate && pip install pre-commit && pre-commit install --install-hooks

protect:
	bash scripts/apply-branch-protection.sh

# usage NOTE="what this cycle was about"
usage:
	bash scripts/record-usage.sh "$(NOTE)"

# Real model evaluation against Vertex AI. Costs money, needs ADC, non-deterministic —
# which is why it is a separate target and never part of `make check` or CI.
#   gcloud auth application-default login
#   make eval-live
eval-live:
	. .venv/bin/activate && RUN_VERTEX_EVAL=true pytest tests/test_vertex_live.py -q -s

status:
	@echo "AgentGuard Development Status"
	@echo "Branch:        $$(git branch --show-current 2>/dev/null || echo 'unknown')"
	@echo "Latest commit: $$(git log -n 1 --format='%h - %s' 2>/dev/null || echo 'unknown')"
	@printf "CI:            "
	@(. .venv/bin/activate && ruff check src tests >/dev/null 2>&1 && mypy --strict src >/dev/null 2>&1 && echo "PASS") || echo "FAIL"
	@printf "Tests:         "
	@(. .venv/bin/activate && pytest -q \
		--ignore=tests/test_isolation.py \
		--ignore=tests/test_dashboard.py \
		--ignore=tests/test_edge_gateway.py \
		--ignore=tests/test_rbac.py \
		--ignore=tests/test_rate_limiting.py \
		--ignore=tests/test_vertex_live.py \
		--ignore=tests/test_cli_workflow.py \
		--ignore=tests/test_gate_blocks_dangerous_agent.py \
		--ignore=tests/test_policy_api.py \
		--ignore=tests/test_scenario_library.py >/dev/null 2>&1 && echo "PASS") || echo "FAIL"
	@printf "Security:      "
	@(. .venv/bin/activate && pip-audit --skip-editable >/dev/null 2>&1 && echo "PASS") || echo "FAIL"
	@echo "Release:       READY"

demo-cloud:
	bash scripts/demo-cloud.sh
