# AuralTrans 2.0

Speaker-attributed transcription with word-level timestamps and grounded, citable insights.
Built from the AuralTrans 2.0 Rebuild Blueprint. Status: Phase 0 (foundations).

## Dev setup
1. `docker compose up -d postgres`
2. `cp .env.example .env`
3. `cd backend && python -m uv sync`
4. `python -m uv run alembic upgrade head`
5. `python -m uv run pytest`
