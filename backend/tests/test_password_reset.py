"""Password reset over HTTP.

What is actually being pinned down here is not "a token works". It is
the set of properties that make a reset link safe to put in somebody's
inbox: one use, a short life, no way to read account existence off the
response, and a ceiling on how often our server will mail an address on
a stranger's say-so.

Addresses use example.com. EmailStr rejects reserved TLDs like .test,
which is documented at the top of test_auth.py and worth not
rediscovering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import PasswordResetRequest, Session, User
from app.services import mail as mail_service
from app.services import password_reset

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

OWNER = "owner@example.com"
PASSWORD = "sangat-rahasia-123"
NEW_PASSWORD = "lebih-rahasia-456"


@pytest.fixture
def mailer():
    """Collect mail instead of sending it, and restore the real one."""
    fake = mail_service.FakeMailer()
    mail_service.set_mailer(fake)
    yield fake
    mail_service.set_mailer(None)


@pytest.fixture
def api(engine, monkeypatch, reset_tables, mailer):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": OWNER, "password": PASSWORD}
        ).raise_for_status()
        client.factory = factory
        yield client

    reset_tables(factory)


def _token_for(factory, email: str) -> str | None:
    """Read the raw token back is impossible by design, so tests mint
    their own through the service and assert on the stored row."""
    with factory() as db:
        return db.scalar(
            select(PasswordResetRequest.token_hash)
            .where(PasswordResetRequest.email == email)
            .order_by(PasswordResetRequest.created_at.desc())
        )


def _issue(factory, email: str, *, now: datetime | None = None) -> str:
    """Issue a token through the service and return the raw value."""
    with factory() as db:
        _, raw = password_reset.request_reset(db, email=email, now=now)
        db.commit()
    assert raw is not None
    return raw


# ----------------------------------------------------------------------
# The uniform answer
# ----------------------------------------------------------------------


def test_unknown_address_answers_exactly_like_a_known_one(api):
    known = api.post("/auth/forgot-password", json={"email": OWNER})
    unknown = api.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.content == unknown.content


def test_an_unknown_address_is_still_recorded_but_gets_no_token(api):
    api.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    with api.factory() as db:
        row = db.scalar(
            select(PasswordResetRequest).where(PasswordResetRequest.email == "nobody@example.com")
        )

    assert row is not None, "the row is what the throttle counts; without it the limit is blind"
    assert row.user_id is None
    assert row.token_hash is None


def test_only_the_known_address_is_mailed(api, mailer):
    api.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert mailer.sent == []

    api.post("/auth/forgot-password", json={"email": OWNER})
    assert [to for to, _ in mailer.sent] == [OWNER]
    assert mailer.sent[0][1].subject == "Bikin password baru"


def test_the_mail_carries_a_usable_link_and_both_parts(api, mailer):
    api.post("/auth/forgot-password", json={"email": OWNER})
    _, message = mailer.sent[0]

    assert "/auth/reset?token=" in message.html
    assert "/auth/reset?token=" in message.text
    assert "{{" not in message.html and "{{" not in message.text


# ----------------------------------------------------------------------
# The token itself
# ----------------------------------------------------------------------


def test_a_token_works_once(api):
    raw = _issue(api.factory, OWNER)

    first = api.post("/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})
    second = api.post("/auth/reset-password", json={"token": raw, "new_password": "lain-lagi-789"})

    assert first.status_code == 204
    assert second.status_code == 400
    assert second.json()["detail"]["code"] == "invalid_reset_token"


def test_an_expired_token_is_refused(api):
    stale = datetime.now(timezone.utc) - timedelta(hours=2)
    raw = _issue(api.factory, OWNER, now=stale)

    response = api.post("/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})

    assert response.status_code == 400


def test_a_made_up_token_is_refused(api):
    response = api.post(
        "/auth/reset-password", json={"token": "tidak-pernah-ada", "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 400


def test_asking_again_retires_the_previous_link(api):
    first = _issue(api.factory, OWNER)
    second = _issue(api.factory, OWNER)

    stale = api.post("/auth/reset-password", json={"token": first, "new_password": NEW_PASSWORD})
    fresh = api.post("/auth/reset-password", json={"token": second, "new_password": NEW_PASSWORD})

    assert stale.status_code == 400, "a link the user has forgotten about must stop working"
    assert fresh.status_code == 204


def test_the_raw_token_is_never_stored(api):
    raw = _issue(api.factory, OWNER)
    stored = _token_for(api.factory, OWNER)

    assert stored is not None
    assert stored != raw
    assert len(stored) == 64


# ----------------------------------------------------------------------
# What a reset does to the account
# ----------------------------------------------------------------------


def test_reset_changes_the_password(api):
    raw = _issue(api.factory, OWNER)
    api.post("/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})

    api.cookies.clear()

    assert api.post("/auth/login", json={"email": OWNER, "password": PASSWORD}).status_code == 401
    assert (
        api.post("/auth/login", json={"email": OWNER, "password": NEW_PASSWORD}).status_code == 200
    )


def test_reset_throws_every_other_device_out(api):
    # The fixture's own session is live; this is the one being revoked.
    assert api.get("/auth/me").status_code == 200

    raw = _issue(api.factory, OWNER)
    api.post("/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})

    assert api.get("/auth/me").status_code == 401

    with api.factory() as db:
        live = db.scalars(select(Session).where(Session.revoked_at.is_(None))).all()

    assert live == []


def test_reset_does_not_hand_back_a_session(api):
    raw = _issue(api.factory, OWNER)
    response = api.post("/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})

    assert response.status_code == 204
    assert "duitakuh_session" not in response.text
    assert api.get("/auth/me").status_code == 401


def test_reset_clears_a_lockout(api):
    """Somebody who forgot their password usually guessed a few times first."""
    api.cookies.clear()
    for _ in range(8):
        api.post("/auth/login", json={"email": OWNER, "password": "salah-terus-123"})

    assert api.post("/auth/login", json={"email": OWNER, "password": PASSWORD}).status_code == 429

    raw = _issue(api.factory, OWNER)
    api.post("/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})

    assert (
        api.post("/auth/login", json={"email": OWNER, "password": NEW_PASSWORD}).status_code == 200
    )


def test_reset_tells_the_account_holder(api, mailer):
    raw = _issue(api.factory, OWNER)
    api.post("/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})

    assert [message.subject for _, message in mailer.sent] == ["Password akun lu baru diganti"]


# ----------------------------------------------------------------------
# The throttle
# ----------------------------------------------------------------------


def test_a_fourth_request_in_the_window_is_refused(api):
    for _ in range(password_reset.MAX_REQUESTS):
        assert api.post("/auth/forgot-password", json={"email": OWNER}).status_code == 202

    response = api.post("/auth/forgot-password", json={"email": OWNER})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"


def test_the_throttle_also_covers_addresses_with_no_account(api):
    """Otherwise the endpoint is a free way to mail-bomb a stranger."""
    for _ in range(password_reset.MAX_REQUESTS):
        api.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert (
        api.post("/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 429
    )


def test_the_throttle_is_per_address(api):
    for _ in range(password_reset.MAX_REQUESTS):
        api.post("/auth/forgot-password", json={"email": OWNER})

    assert api.post("/auth/forgot-password", json={"email": "lain@example.com"}).status_code == 202


def test_a_refused_request_does_not_extend_the_lockout(api):
    """A 429 must not write a row of its own.

    If it did, every refused attempt would push the window forward and
    the address would stay locked for as long as anyone kept knocking.
    Note this does not exercise the commit-before-raise in the handler:
    nothing is pending at the point it raises. That commit is there so
    the trap stays shut if a write is ever added above it, the way the
    sign-in throttle was once silently rolled back.
    """
    for _ in range(password_reset.MAX_REQUESTS + 2):
        api.post("/auth/forgot-password", json={"email": OWNER})

    with api.factory() as db:
        rows = db.scalars(
            select(PasswordResetRequest).where(PasswordResetRequest.email == OWNER)
        ).all()

    assert len(rows) == password_reset.MAX_REQUESTS


# ----------------------------------------------------------------------
# Changing a password deliberately
# ----------------------------------------------------------------------


def test_changing_the_password_also_sends_the_notice(api, mailer):
    response = api.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 204
    assert [message.subject for _, message in mailer.sent] == ["Password akun lu baru diganti"]


def test_a_user_who_is_gone_cannot_be_reset(api):
    raw = _issue(api.factory, OWNER)

    with api.factory() as db:
        db.query(Session).delete()
        db.query(User).delete()
        db.commit()

    assert (
        api.post(
            "/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD}
        ).status_code
        == 400
    )
