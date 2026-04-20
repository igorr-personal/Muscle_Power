"""Database engine, session factory, and connection management."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as DBSession, sessionmaker

from muscle_power.db.models import Base
from muscle_power.utils.errors import DatabaseError
from muscle_power.utils.logger import get_logger

_log = get_logger(__name__)


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine(database_url: str | None = None) -> Engine:
    global _engine
    if _engine is None:
        from muscle_power.utils.config import get_config

        url = database_url or get_config().database.url

        if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
            db_path = Path(url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        if url.startswith("sqlite"):
            _configure_sqlite(_engine)
        safe_url = url.split("@")[-1] if "@" in url else url
        _log.info("Database engine created (%s)", safe_url)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def db_session() -> Generator[DBSession, None, None]:
    """Provide a transactional database session with automatic rollback."""
    session: DBSession = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        raise DatabaseError(f"Database operation failed: {exc}") from exc
    finally:
        session.close()


def init_db() -> None:
    """Create all tables if they do not exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _log.info("Database schema initialised")


def reset_engine() -> None:
    """Drop cached engine — used after settings changes or in tests."""
    global _engine, _SessionFactory
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
