"""Test fixtures.

Integration tests need a real PostgreSQL: the guarantees they check —
unique-constraint idempotency, rollback atomicity, enum and check
constraints — are properties of the database, so testing them against a
substitute would prove nothing about production.

They are skipped, not failed, when ``TEST_DATABASE_URL`` is unset, so the
pure domain suite still runs anywhere.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; see backend/README.md",
)


@pytest.fixture(scope="session")
def engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")

    from sqlalchemy import create_engine

    from app.models import Base

    eng = create_engine(TEST_DATABASE_URL, future=True)

    # Rebuild from scratch so a half-migrated database cannot make a test
    # pass or fail for the wrong reason.
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)

    yield eng

    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator:
    """A session rolled back after each test, so tests cannot leak into each other.

    The outer transaction is never committed: the test's own commits land
    in a nested SAVEPOINT, which is discarded at the end.
    """
    from sqlalchemy.orm import Session

    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def user(session):
    """A persisted user to own test data."""
    from app.models import User

    u = User(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4().hex[:8]}@example.test",
        password_hash="not-a-real-hash",
    )
    session.add(u)
    session.flush()
    return u


@pytest.fixture
def other_user(session):
    """A second user, for proving isolation (AC08)."""
    from app.models import User

    u = User(
        id=uuid.uuid4(),
        email=f"other-{uuid.uuid4().hex[:8]}@example.test",
        password_hash="not-a-real-hash",
    )
    session.add(u)
    session.flush()
    return u
