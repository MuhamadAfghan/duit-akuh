"""Test fixtures.

Integration tests need a real database: the guarantees they check —
unique-constraint idempotency, rollback atomicity, enum and check
constraints — are properties of the engine, so testing them against a
substitute would prove nothing about production.

Either engine works. PostgreSQL is the better fit for this schema, but
production runs on MariaDB 10.6 (the cPanel host has no PostgreSQL), so
``TEST_DATABASE_URL`` should point at MySQL when the point is to verify
what actually ships. ``app.types`` is what keeps the two equivalent.

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

    from sqlalchemy import create_engine, event

    from app.db import _harden_mysql_session
    from app.models import Base

    eng = create_engine(TEST_DATABASE_URL, future=True)

    # The application engine pins UTC and strict mode per connection; the
    # tests build their own engine, so they have to do the same or they
    # would be testing a laxer database than production runs.
    if eng.dialect.name == "mysql":
        event.listen(eng, "connect", _harden_mysql_session)

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


@pytest.fixture
def reset_tables():
    """Empty every table the API tests write to, between tests.

    Returns a callable so the API fixtures can run it during teardown
    against their own session factory.

    Self-referential foreign keys have to be broken before the delete.
    ``transactions.reverses_id``, ``accounts.linked_account_id`` and
    ``messages.reply_to_id`` all reference their own table. PostgreSQL checks
    that at the end of the statement, so a bulk ``DELETE`` over the whole
    table succeeds; MySQL checks row by row in an unspecified order and
    aborts with "Cannot delete or update a parent row" the moment it
    reaches a parent before its child. Nulling the two columns first
    works on both engines and leaves the constraints enforced — which is
    the point of having them in a test database at all.
    """

    def _reset(factory) -> None:
        from app.models import (
            Account,
            Allocation,
            AuditEvent,
            Budget,
            Entry,
            Goal,
            LoginAttempt,
            Message,
            PasswordResetRequest,
            Session,
            Transaction,
            User,
        )

        with factory() as cleanup:
            cleanup.query(Transaction).update(
                {Transaction.reverses_id: None}, synchronize_session=False
            )
            cleanup.query(Account).update(
                {Account.linked_account_id: None}, synchronize_session=False
            )
            cleanup.query(Message).update({Message.reply_to_id: None}, synchronize_session=False)

            for model in (
                AuditEvent,
                Entry,
                Transaction,
                Budget,
                Allocation,
                Goal,
                Account,
                Session,
                LoginAttempt,
                PasswordResetRequest,
                User,
            ):
                cleanup.query(model).delete()

            cleanup.commit()

    return _reset


# ----------------------------------------------------------------------
# The chat client
# ----------------------------------------------------------------------

PASSWORD = "sangat-rahasia-123"


@pytest.fixture
def chat(engine, monkeypatch):
    """TestClient with a registered user and a scripted adapter attached."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.api import routes_chat
    from app.main import app
    from app.models import (
        Account,
        AiRequestLog,
        Allocation,
        AuditEvent,
        Conversation,
        Draft,
        Entry,
        Goal,
        LoginAttempt,
        Message,
        Session,
        Transaction,
        User,
    )

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    from app.services.ai.fake import FakeAdapter

    adapter = FakeAdapter()
    routes_chat.set_adapter(adapter)

    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "chat@example.com", "password": PASSWORD}
        ).raise_for_status()
        client.adapter = adapter
        yield client

    routes_chat.set_adapter(None)

    with factory() as cleanup:
        for model in (
            AiRequestLog,
            Message,
            Conversation,
            AuditEvent,
            Entry,
            Draft,
            Transaction,
            Allocation,
            Goal,
            Account,
            Session,
            LoginAttempt,
            User,
        ):
            cleanup.query(model).delete()
        cleanup.commit()


def make_account(chat, name, type_="bank", *, balance=0, alias=None):
    body = {"name": name, "type": type_, "opening_balance": balance}
    if alias:
        body["alias"] = alias
    response = chat.post("/accounts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def balances(chat) -> dict[str, int]:
    return {a["name"]: a["balance"] for a in chat.get("/accounts").json()}


def send(chat, body: str) -> dict:
    response = chat.post("/chat/messages", json={"body": body})
    assert response.status_code == 200, response.text
    return response.json()
