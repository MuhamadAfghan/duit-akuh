"""Password reset by emailed link.

Three decisions carry the security of this flow, and each is easy to
undo by accident:

* **The endpoint answers the same for every address.** A row is written
  whether or not the account exists, and the route returns 202 either
  way. A page that says "no such email" is a tool for finding out who
  has an account here.
* **Only the token's hash is stored**, exactly as for session tokens.
  A database leak must not hand anyone a working reset link.
* **A token is single use and short lived**, and issuing a new one
  retires the old. Reset links end up in inboxes, chat history and
  browser history; the window in which a leaked one still works has to
  be small.

The throttle counts rows rather than keeping state in memory, which is
the same technique as the sign-in throttle in ``auth.py``: it holds
across worker processes and survives a restart.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DbSession

from ..models import PasswordResetRequest, User
from . import auth as auth_service

#: How long a link works. Long enough to find the mail and act on it,
#: short enough that a forwarded or logged URL goes stale quickly.
TOKEN_LIFETIME = timedelta(minutes=60)

#: Throttle, counted per address. Asking again is cheap for a person who
#: mistyped their address once; it is also how you would spam somebody
#: else's inbox using our server, so it has a ceiling.
REQUEST_WINDOW = timedelta(minutes=15)
MAX_REQUESTS = 3


class ResetError(Exception):
    """Base for password-reset failures."""

    code = "reset_error"


class TooManyRequests(ResetError):
    """Too many reset requests for one address in the window."""

    code = "too_many_requests"

    def __init__(self, message: str = "Terlalu banyak permintaan. Coba lagi nanti.") -> None:
        super().__init__(message)


class InvalidToken(ResetError):
    """Unknown, expired, or already-used token."""

    code = "invalid_reset_token"

    def __init__(self, message: str = "Tautannya sudah tidak berlaku.") -> None:
        super().__init__(message)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _recent_requests(db: DbSession, email: str, now: datetime) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(PasswordResetRequest)
            .where(
                PasswordResetRequest.email == email,
                PasswordResetRequest.created_at > now - REQUEST_WINDOW,
            )
        )
        or 0
    )


def request_reset(
    db: DbSession, *, email: str, now: datetime | None = None
) -> tuple[PasswordResetRequest, str | None]:
    """Record a reset request and issue a token if the account exists.

    Returns the row and the **raw** token, which is the only moment it
    exists in readable form. The token is ``None`` when the address has
    no account — the caller still gets a row, still returns 202, and
    simply has no mail to send.
    """
    now = now or datetime.now(timezone.utc)
    email = auth_service.normalise_email(email)

    if _recent_requests(db, email, now) >= MAX_REQUESTS:
        raise TooManyRequests

    user = db.scalar(select(User).where(User.email == email))

    raw_token: str | None = None
    token_hash: str | None = None
    expires_at: datetime | None = None

    if user is not None and user.is_active:
        # Retire anything still outstanding. Two live links for one
        # account means a link the user has forgotten about still works.
        db.execute(
            update(PasswordResetRequest)
            .where(
                PasswordResetRequest.user_id == user.id,
                PasswordResetRequest.used_at.is_(None),
                PasswordResetRequest.token_hash.is_not(None),
            )
            .values(used_at=now)
        )

        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_token)
        expires_at = now + TOKEN_LIFETIME

    row = PasswordResetRequest(
        email=email,
        user_id=user.id if user is not None else None,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    db.add(row)
    db.flush()

    return row, raw_token


def consume_token(
    db: DbSession, *, raw_token: str, new_password: str, now: datetime | None = None
) -> User:
    """Spend a reset token and set the new password.

    Revokes every session afterwards. That is the point of a reset: if
    somebody else got in with the old password, this is what puts them
    out.
    """
    now = now or datetime.now(timezone.utc)

    if not raw_token:
        raise InvalidToken

    row = db.scalar(
        select(PasswordResetRequest).where(
            PasswordResetRequest.token_hash == _hash_token(raw_token)
        )
    )

    if row is None or not row.is_redeemable(now) or row.user_id is None:
        raise InvalidToken

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise InvalidToken

    # Validates length before anything is written.
    user.password_hash = auth_service.hash_password(new_password)
    row.used_at = now

    db.flush()

    auth_service.revoke_all_sessions(db, user.id, now=now)
    # A reset is also the end of a run of failed sign-ins. Leaving them
    # would lock the account the person just recovered.
    auth_service.clear_failures(db, user.email)

    return user
