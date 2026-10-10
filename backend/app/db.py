"""Database engine and session handling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _harden_mysql_session(dbapi_connection, connection_record) -> None:
    """Pin UTC and strict mode on every MySQL/MariaDB connection.

    Both are correctness requirements, not tuning:

    * ``time_zone = '+00:00'`` — MariaDB has no timezone-aware column
      type, so ``app.types.UtcDateTime`` stores UTC and reattaches the
      offset on the way out. A server-side ``CURRENT_TIMESTAMP`` default
      follows the *session* zone, and the deployment host's system zone
      is WIB (+07), so without this pin server-defaulted rows would come
      back seven hours wrong.
    * ``STRICT_ALL_TABLES`` — outside strict mode MySQL truncates and
      coerces out-of-range values with a warning instead of an error. In
      a ledger a silently truncated amount is the worst possible
      failure; FR03 wants the write refused.
    """
    cursor = dbapi_connection.cursor()

    try:
        cursor.execute(
            "SET SESSION time_zone = '+00:00', "
            "sql_mode = 'STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION'"
        )
    finally:
        cursor.close()


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            # Recycle before typical idle timeouts and verify liveness, so a
            # dropped connection surfaces as a retry rather than a 500.
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
        )

        if _engine.dialect.name == "mysql":
            event.listen(_engine, "connect", _harden_mysql_session)

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory

    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
            future=True,
        )

    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """One unit of work: commit on success, roll back on any exception.

    Financial writes must be all-or-nothing (FR03, AC13), so there is no
    partial-commit path here by design.
    """
    session = get_session_factory()()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency wrapping :func:`session_scope`."""
    with session_scope() as session:
        yield session
