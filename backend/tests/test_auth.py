"""Authentication: the service rules and the HTTP surface.

Addresses use ``example.com``: ``EmailStr`` rejects reserved TLDs such as
``.test``, so the HTTP tests would fail validation before reaching any
logic under test.

These go beyond the happy path on purpose. The things most worth proving
here are the ones that fail silently when wrong — that the cookie really
is httpOnly, that a token is not recoverable from the database, that
logout actually revokes, and that sign-in does not reveal who has an
account.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import LoginAttempt, Session, User
from app.services import auth as auth_service

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "sangat-rahasia-123"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(engine, monkeypatch):
    """A TestClient bound to the test database, with cookies persisted."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as c:
        yield c

    # The HTTP tests commit through the app's own sessions, so they cannot
    # ride the outer-rollback fixture; clean up explicitly instead.
    with factory() as cleanup:
        for model in (Session, LoginAttempt, User):
            cleanup.query(model).delete()
        cleanup.commit()


# ----------------------------------------------------------------------
# Password hashing
# ----------------------------------------------------------------------


def test_password_is_hashed_with_argon2id_not_stored_plain(session):
    user = auth_service.register_user(session, email="a@example.com", password=PASSWORD)

    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2id$"), "must be argon2id, not a weaker variant"


def test_same_password_produces_different_hashes(session):
    a = auth_service.register_user(session, email="a@example.com", password=PASSWORD)
    b = auth_service.register_user(session, email="b@example.com", password=PASSWORD)

    assert a.password_hash != b.password_hash, "hashes must be individually salted"


@pytest.mark.parametrize("bad", ["short", "a" * 7])
def test_short_passwords_are_rejected(session, bad):
    with pytest.raises(auth_service.WeakPassword):
        auth_service.register_user(session, email="a@example.com", password=bad)


def test_absurdly_long_password_is_rejected(session):
    """An unbounded password is a cheap way to make the server hash forever."""
    with pytest.raises(auth_service.WeakPassword):
        auth_service.register_user(session, email="a@example.com", password="a" * 5000)


def test_email_is_normalised(session):
    user = auth_service.register_user(session, email="  MiXeD@Example.COM ", password=PASSWORD)
    assert user.email == "mixed@example.com"

    # And sign-in matches regardless of how it is typed.
    assert (
        auth_service.authenticate(session, email="MIXED@EXAMPLE.COM", password=PASSWORD).id
        == user.id
    )


def test_duplicate_registration_is_rejected(session):
    auth_service.register_user(session, email="a@example.com", password=PASSWORD)

    with pytest.raises(auth_service.EmailAlreadyRegistered):
        auth_service.register_user(session, email="A@example.com", password=PASSWORD)


# ----------------------------------------------------------------------
# Sign-in
# ----------------------------------------------------------------------


def test_wrong_password_and_unknown_email_give_the_same_error(session):
    auth_service.register_user(session, email="a@example.com", password=PASSWORD)

    with pytest.raises(auth_service.InvalidCredentials) as wrong:
        auth_service.authenticate(session, email="a@example.com", password="wrong-password-x")

    with pytest.raises(auth_service.InvalidCredentials) as unknown:
        auth_service.authenticate(session, email="nobody@example.com", password=PASSWORD)

    # Identical message: anything else lets an attacker enumerate accounts.
    assert str(wrong.value) == str(unknown.value)


def test_inactive_user_cannot_sign_in(session):
    user = auth_service.register_user(session, email="a@example.com", password=PASSWORD)
    user.is_active = False
    session.flush()

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.authenticate(session, email="a@example.com", password=PASSWORD)


def test_successful_sign_in_clears_earlier_failures(session):
    auth_service.register_user(session, email="a@example.com", password=PASSWORD)

    for _ in range(3):
        with pytest.raises(auth_service.InvalidCredentials):
            auth_service.authenticate(session, email="a@example.com", password="nope-nope-nope")

    auth_service.authenticate(session, email="a@example.com", password=PASSWORD)

    remaining = session.scalars(
        select(LoginAttempt).where(LoginAttempt.email == "a@example.com")
    ).all()
    assert remaining == []


# ----------------------------------------------------------------------
# Throttling (PRD section 9)
# ----------------------------------------------------------------------


def test_repeated_failures_lock_further_attempts(session):
    auth_service.register_user(session, email="a@example.com", password=PASSWORD)

    for _ in range(auth_service.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth_service.InvalidCredentials):
            auth_service.authenticate(session, email="a@example.com", password="wrong-pass-123")

    # Even the correct password is refused once the threshold is hit.
    with pytest.raises(auth_service.TooManyAttempts):
        auth_service.authenticate(session, email="a@example.com", password=PASSWORD)


def test_throttling_applies_to_addresses_that_do_not_exist(session):
    """Otherwise the lockout itself reveals which addresses are registered."""
    for _ in range(auth_service.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth_service.InvalidCredentials):
            auth_service.authenticate(session, email="ghost@example.com", password="wrong-pass-1")

    with pytest.raises(auth_service.TooManyAttempts):
        auth_service.authenticate(session, email="ghost@example.com", password="wrong-pass-1")


def test_old_failures_fall_outside_the_window(session):
    auth_service.register_user(session, email="a@example.com", password=PASSWORD)

    for _ in range(auth_service.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth_service.InvalidCredentials):
            auth_service.authenticate(session, email="a@example.com", password="wrong-pass-123")

    later = datetime.now(timezone.utc) + auth_service.LOGIN_WINDOW + timedelta(minutes=1)
    user = auth_service.authenticate(session, email="a@example.com", password=PASSWORD, now=later)

    assert user.email == "a@example.com"


# ----------------------------------------------------------------------
# Sessions
# ----------------------------------------------------------------------


def test_raw_token_is_never_stored(session):
    user = auth_service.register_user(session, email="a@example.com", password=PASSWORD)
    record, raw_token = auth_service.create_session(session, user=user)

    assert record.token_hash != raw_token
    assert record.token_hash == hashlib.sha256(raw_token.encode()).hexdigest()

    # Nothing anywhere in the row holds the usable token.
    assert raw_token not in str(record.__dict__)


def test_session_resolves_then_stops_after_logout(session):
    user = auth_service.register_user(session, email="a@example.com", password=PASSWORD)
    record, raw_token = auth_service.create_session(session, user=user)

    resolved_session, resolved_user = auth_service.resolve_session(session, raw_token)
    assert resolved_user.id == user.id

    auth_service.revoke_session(session, resolved_session)

    with pytest.raises(auth_service.NotAuthenticated):
        auth_service.resolve_session(session, raw_token)


def test_expired_session_is_rejected(session):
    user = auth_service.register_user(session, email="a@example.com", password=PASSWORD)
    _, raw_token = auth_service.create_session(session, user=user)

    later = datetime.now(timezone.utc) + auth_service.SESSION_LIFETIME + timedelta(seconds=1)

    with pytest.raises(auth_service.NotAuthenticated):
        auth_service.resolve_session(session, raw_token, now=later)


@pytest.mark.parametrize("token", [None, "", "not-a-real-token"])
def test_missing_or_bogus_tokens_are_rejected(session, token):
    with pytest.raises(auth_service.NotAuthenticated):
        auth_service.resolve_session(session, token)


def test_changing_the_password_revokes_every_session(session):
    user = auth_service.register_user(session, email="a@example.com", password=PASSWORD)
    _, token_a = auth_service.create_session(session, user=user)
    _, token_b = auth_service.create_session(session, user=user)

    auth_service.change_password(
        session, user=user, current_password=PASSWORD, new_password="kata-sandi-baru-9"
    )

    for token in (token_a, token_b):
        with pytest.raises(auth_service.NotAuthenticated):
            auth_service.resolve_session(session, token)

    assert auth_service.authenticate(session, email="a@example.com", password="kata-sandi-baru-9")


def test_change_password_requires_the_current_one(session):
    user = auth_service.register_user(session, email="a@example.com", password=PASSWORD)

    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.change_password(
            session, user=user, current_password="wrong-one-here", new_password="kata-sandi-baru-9"
        )


def test_one_users_session_never_resolves_to_another(session):
    a = auth_service.register_user(session, email="a@example.com", password=PASSWORD)
    b = auth_service.register_user(session, email="b@example.com", password=PASSWORD)

    _, token_a = auth_service.create_session(session, user=a)
    _, token_b = auth_service.create_session(session, user=b)

    assert auth_service.resolve_session(session, token_a)[1].id == a.id
    assert auth_service.resolve_session(session, token_b)[1].id == b.id


# ----------------------------------------------------------------------
# HTTP surface
# ----------------------------------------------------------------------


def test_register_sets_an_httponly_cookie_and_returns_no_token(client):
    response = client.post(
        "/auth/register", json={"email": "http@example.com", "password": PASSWORD}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "http@example.com"

    # The credential must not be in the body - only in the cookie.
    assert "token" not in response.text.lower()

    cookie_header = response.headers["set-cookie"]
    assert "httponly" in cookie_header.lower(), "page scripts must not be able to read it"
    assert "samesite=lax" in cookie_header.lower()
    assert "path=/" in cookie_header.lower()


def test_me_requires_a_session(client):
    assert client.get("/auth/me").status_code == 401


def test_login_then_me_then_logout(client):
    client.post("/auth/register", json={"email": "flow@example.com", "password": PASSWORD})
    client.post("/auth/logout")

    assert client.get("/auth/me").status_code == 401

    login = client.post("/auth/login", json={"email": "flow@example.com", "password": PASSWORD})
    assert login.status_code == 200

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "flow@example.com"

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_login_with_wrong_password_is_401(client):
    client.post("/auth/register", json={"email": "wrong@example.com", "password": PASSWORD})
    client.post("/auth/logout")

    response = client.post(
        "/auth/login", json={"email": "wrong@example.com", "password": "definitely-wrong-1"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


def test_duplicate_registration_is_409(client):
    client.post("/auth/register", json={"email": "dupe@example.com", "password": PASSWORD})

    response = client.post(
        "/auth/register", json={"email": "dupe@example.com", "password": PASSWORD}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "email_already_registered"


def test_short_password_is_rejected_before_reaching_the_service(client):
    response = client.post("/auth/register", json={"email": "x@example.com", "password": "abc"})
    assert response.status_code == 422


def test_invalid_email_is_rejected(client):
    response = client.post("/auth/register", json={"email": "not-an-email", "password": PASSWORD})
    assert response.status_code == 422


def test_a_stale_cookie_stops_working_after_logout(client):
    client.post("/auth/register", json={"email": "stale@example.com", "password": PASSWORD})
    stolen = client.cookies.get(auth_service.SESSION_COOKIE_NAME)

    client.post("/auth/logout")
    client.cookies.set(auth_service.SESSION_COOKIE_NAME, stolen)

    assert client.get("/auth/me").status_code == 401


def test_throttling_actually_applies_over_http(client):
    """Regression guard.

    The throttle counter is written during a request that then raises, so
    the session is rolled back unless the handler commits first. It did
    not, and the lockout required by PRD section 9 silently counted
    nothing - while the service-level test still passed, because it never
    went through a request's transaction boundary.
    """
    client.post("/auth/register", json={"email": "throttle@example.com", "password": PASSWORD})
    client.post("/auth/logout")

    codes = [
        client.post(
            "/auth/login",
            json={"email": "throttle@example.com", "password": "wrong-password-xx"},
        ).status_code
        for _ in range(auth_service.MAX_FAILED_ATTEMPTS + 1)
    ]

    assert codes[0] == 401
    assert codes[-1] == 429, (
        f"expected a lockout after {auth_service.MAX_FAILED_ATTEMPTS}, got {codes}"
    )

    # The correct password is refused too while the lockout holds.
    locked = client.post(
        "/auth/login", json={"email": "throttle@example.com", "password": PASSWORD}
    )
    assert locked.status_code == 429
    assert locked.json()["detail"]["code"] == "too_many_attempts"


def test_session_cookie_is_marked_secure_in_production(engine, monkeypatch):
    """`Secure` is off only for local HTTP; production must set it."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.api import routes_auth
    from app.config import Settings
    from app.main import app
    from app.models import LoginAttempt, Session, User

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    production = Settings(
        database_url="postgresql+psycopg://unused",
        app_env="production",
        cors_origins=(),
        llm_base_url=None,
        llm_model="qwen3.5-9b",
        stt_base_url=None,
    )
    monkeypatch.setattr(routes_auth, "get_settings", lambda: production)

    with TestClient(app) as c:
        response = c.post(
            "/auth/register", json={"email": "secure@example.com", "password": PASSWORD}
        )

    assert response.status_code == 201
    assert "secure" in response.headers["set-cookie"].lower()

    with factory() as cleanup:
        for model in (Session, LoginAttempt, User):
            cleanup.query(model).delete()
        cleanup.commit()
