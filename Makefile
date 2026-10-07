.PHONY: db test lint migrate

db:
	docker compose up -d postgres

test:
	cd backend && python -m uv run pytest

lint:
	cd backend && python -m uv run ruff check . && python -m uv run mypy src

migrate:
	cd backend && python -m uv run alembic upgrade head
