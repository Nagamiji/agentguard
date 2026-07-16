.PHONY: help install hooks up down migrate dev worker test lint typecheck check fmt protect usage

help:
	@echo "install   - create venv + install dev deps"
	@echo "hooks     - install pre-commit hooks (incl. commit-msg)"
	@echo "up/down   - start/stop local Postgres+Redis (docker compose)"
	@echo "migrate   - apply database migrations (alembic upgrade head)"
	@echo "dev       - run the API (uvicorn, reload)"
	@echo "worker    - run the worker"
	@echo "test      - pytest"
	@echo "lint      - ruff check + format check"
	@echo "typecheck - mypy --strict"
	@echo "check     - lint + typecheck + test (what CI runs)"
	@echo "protect   - apply GitHub branch protection to main (needs gh admin auth)"
	@echo "usage     - record today's token usage to reports/usage/ (NOTE=\"...\")"

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
