"""Shared fixtures. DB tests use a throwaway database per test and skip if Postgres is not running."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from auraltrans.config import settings
from auraltrans.db import session as dbsession
from auraltrans.db.models import Base
from auraltrans.storage.local import LocalStorage

_BASE_URL = settings.database_url.rsplit("/", 1)[0]


@pytest.fixture
def db() -> Iterator[Engine]:
    name = f"auraltrans_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(f"{_BASE_URL}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # noqa: BLE001 - any connection problem means "no database here"
        admin.dispose()
        pytest.skip(f"Postgres is not reachable ({type(exc).__name__}); run `docker compose up -d postgres`")
    engine = create_engine(f"{_BASE_URL}/{name}")
    Base.metadata.create_all(engine)
    dbsession.set_engine(engine)
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")
