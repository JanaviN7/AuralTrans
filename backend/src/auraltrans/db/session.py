"""Engine and session handling. The engine is created lazily so tests can swap it."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from auraltrans.config import settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def set_engine(engine: Engine) -> None:
    """Use a specific engine (tests point this at a throwaway database)."""
    global _engine, _factory
    _engine = engine
    _factory = sessionmaker(engine, expire_on_commit=False)


def get_engine() -> Engine:
    if _engine is None:
        set_engine(create_engine(settings.database_url, pool_pre_ping=True))
    assert _engine is not None
    return _engine


def _sessions() -> sessionmaker[Session]:
    get_engine()
    assert _factory is not None
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit on success, roll back on error."""
    session = _sessions()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session
