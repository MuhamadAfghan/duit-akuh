"""Registration, sign-in, and sessions.

Decisions worth knowing, because they are security-relevant and easy to
undo by accident:

* **Argon2id** for passwords, via ``argon2-cffi``. Verification
  transparently re-hashes when the parameters change, so raising the cost
  later upgrades existing users on their next sign-in.
* **Server-side sessions**, not a JWT in JavaScript. The token lives in an
  httpOnly cookie, so page scripts cannot read it and an XSS bug cannot
  exfiltrate a login. It also makes logout actually revoke, which a
  stateless token cannot.
* **Only the token hash is stored.** A database leak yields nothing usable.
* **Failures are deliberately uniform.** A wrong password and an unknown
  address return the same error, and an unknown address still pays the
  cost of a hash verification, so response time does not reveal who has an
  account.
* **Throttling by address** (PRD section 9): too many recent failures lock
  further attempts for a window, whether or not the address exists.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from ..models import LoginAttempt, Session, User

#: Argon2id with the library's current defaults, which track the RFC 9106
#: recommendations. Raising these later is safe: verify() re-hashes.
_hasher = PasswordHasher()

#: Burned when an address is unknown, so a sign-in attempt costs the same
#: whether or not the account exists. Any valid Argon2 hash works; this is
#: the hash of a value nobody can sign in with.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

SESSION_COOKIE_NAME = "duitakuh_session"
#: Absolute lifetime. There is no sliding renewal: a stolen cookie stays
#: useful for a bounded time rather than indefinitely.
SESSION_LIFETIME = timedelta(days=30)

#: Throttling window and threshold (PRD section 9).
LOGIN_WINDOW = timedelta(minutes=15)
MAX_FAILED_ATTEMPTS = 8

#: Argon2 rejects passwords far longer than this anyway, and an unbounded
#: password is a cheap way to make the server do expensive work.
MAX_PASSWORD_LENGTH = 256
MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Base for authentication failures."""

    code = "auth_error"


class InvalidCredentials(AuthError):
    """Wrong password, unknown address, or a disabled account.

    One error for all three on purpose: distinguishing them would let an
    attacker enumerate who has an account.
    """

    code = "invalid_credentials"


class TooManyAttempts(AuthError):
    code = "too_many_attempts"


class EmailAlreadyRegistered(AuthError):
    code = "email_already_registered"


class WeakPassword(AuthError):
    code = "weak_password"


class NotAuthenticated(AuthError):
    code = "not_authenticated"


def normalise_email(email: str) -> str:
    """Lowercase and trim. Addresses are matched case-insensitively."""
    return email.strip().lower()


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"Kata sandi minimal {MIN_PASSWORD_LENGTH} karakter")

    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(f"Kata sandi maksimal {MAX_PASSWORD_LENGTH} karakter")


def hash_password(password: str) -> str:
    _validate_password(password)
    return _hasher.hash(password)


# ----------------------------------------------------------------------
# Throttling
# ----------------------------------------------------------------------


def _recent_failures(db: DbSession, email: str, now: datetime) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.email == email, LoginAttempt.created_at > now - LOGIN_WINDOW)
        )
        or 0
    )


def _record_failure(db: DbSession, email: str) -> None:
    db.add(LoginAttempt(email=email))
    db.flush()


def clear_failures(db: DbSession, email: str) -> None:
    """Drop an address's failures after a successful sign-in."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
    db.flush()


# ----------------------------------------------------------------------
# Registration and sign-in
# ----------------------------------------------------------------------


def register_user(db: DbSession, *, email: str, password: str) -> User:
    """Create an account.

    Note this *does* reveal whether an address is already registered,
    which sign-in deliberately does not. Hiding it would mean accepting
    the registration silently and confirming by email, which needs mail
    infrastructure the app does not have yet. Worth revisiting before the
    pilot.
    """
    email = normalise_email(email)

    if not email or "@" not in email:
        raise WeakPassword("Alamat email tidak valid")

    existing = db.scalar(select(User).where(User.email == email))

    if existing is not None:
        raise EmailAlreadyRegistered("Email sudah terdaftar")

    user = User(id=uuid.uuid4(), email=email, password_hash=hash_password(password))
    db.add(user)
    db.flush()

    return user


def authenticate(db: DbSession, *, email: str, password: str, now: datetime | None = None) -> User:
    """Verify credentials, or raise.

    Every failure path costs one Argon2 verification so that timing does
    not distinguish "no such user" from "wrong password".
    """
    now = now or datetime.now(timezone.utc)
    email = normalise_email(email)

    if _recent_failures(db, email, now) >= MAX_FAILED_ATTEMPTS:
        raise TooManyAttempts("Terlalu banyak percobaan masuk. Coba lagi dalam beberapa menit.")

    user = db.scalar(select(User).where(User.email == email))

    # Verify against a dummy hash when the address is unknown, so the work
    # done is the same either way.
    stored_hash = user.password_hash if user is not None else _DUMMY_HASH

    try:
        _hasher.verify(stored_hash, password)
        verified = True
    except (VerifyMismatchError, InvalidHashError):
        verified = False

    if not verified or user is None or not user.is_active:
        _record_failure(db, email)
        raise InvalidCredentials("Email atau kata sandi salah")

    # Transparently upgrade the stored hash if the cost parameters changed.
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(password)
        db.flush()

    clear_failures(db, email)

    return user


# ----------------------------------------------------------------------
# Sessions
# ----------------------------------------------------------------------


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(
    db: DbSession,
    *,
    user: User,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> tuple[Session, str]:
    """Open a session.

    :returns: the row and the **raw token**, which is returned exactly
        once. It is never stored, so it cannot be recovered later — only
        handed straight to the cookie.
    """
    now = now or datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(32)

    session = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=now + SESSION_LIFETIME,
        user_agent=(user_agent or "")[:300] or None,
    )

    db.add(session)
    db.flush()

    return session, raw_token


def resolve_session(
    db: DbSession, raw_token: str | None, *, now: datetime | None = None
) -> tuple[Session, User]:
    """Look up a live session by its raw token, or raise."""
    now = now or datetime.now(timezone.utc)

    if not raw_token:
        raise NotAuthenticated("Belum masuk")

    session = db.scalar(select(Session).where(Session.token_hash == _hash_token(raw_token)))

    if session is None or not session.is_valid(now):
        raise NotAuthenticated("Sesi tidak berlaku")

    user = db.get(User, session.user_id)

    if user is None or not user.is_active:
        raise NotAuthenticated("Sesi tidak berlaku")

    session.last_seen_at = now

    return session, user


def revoke_session(db: DbSession, session: Session, *, now: datetime | None = None) -> None:
    """Log out. The row is kept so the history of sessions stays visible."""
    session.revoked_at = now or datetime.now(timezone.utc)
    db.flush()


def revoke_all_sessions(db: DbSession, user_id: uuid.UUID, *, now: datetime | None = None) -> int:
    """Revoke every live session for a user.

    Used after a password change, so an attacker holding an old cookie is
    cut off rather than staying signed in.
    """
    now = now or datetime.now(timezone.utc)

    sessions = db.scalars(
        select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    ).all()

    for session in sessions:
        session.revoked_at = now

    db.flush()

    return len(sessions)


def change_password(db: DbSession, *, user: User, current_password: str, new_password: str) -> None:
    """Change a password, then cut every existing session."""
    try:
        _hasher.verify(user.password_hash, current_password)
    except (VerifyMismatchError, InvalidHashError) as exc:
        raise InvalidCredentials("Kata sandi saat ini salah") from exc

    user.password_hash = hash_password(new_password)
    db.flush()

    revoke_all_sessions(db, user.id)
