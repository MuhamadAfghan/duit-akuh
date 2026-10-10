"""Database engine and session handling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


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
