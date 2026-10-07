.PHONY: db test lint migrate api worker web

db:
	docker compose up -d postgres

test:
	cd backend && python -m uv run --extra speech --extra eval pytest

lint:
	cd backend && python -m uv run ruff check . && python -m uv run mypy src

migrate:
	cd backend && python -m uv run alembic upgrade head

api:
	cd backend && python -m uv run uvicorn auraltrans.api.app:app --port 8765

worker:
	cd backend && python -m uv run python -m auraltrans.worker

web:
	cd web && npm run dev
