.PHONY: help install up down migrate dev worker test lint typecheck check fmt

help:
	@echo "install   - create venv + install dev deps"
	@echo "up/down   - start/stop local Postgres+Redis (docker compose)"
	@echo "migrate   - apply database migrations (alembic upgrade head)"
	@echo "dev       - run the API (uvicorn, reload)"
	@echo "worker    - run the worker"
	@echo "test      - pytest"
	@echo "lint      - ruff check"
	@echo "typecheck - mypy"
	@echo "check     - lint + typecheck + test (what CI runs)"

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
	. .venv/bin/activate && ruff check src tests

typecheck:
	. .venv/bin/activate && mypy src

check: lint typecheck test
