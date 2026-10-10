"""Shared FastAPI dependencies.

``get_current_user`` is the single gate every money endpoint goes
through. There is no development bypass and no "trust this header" path:
AC08 makes zero cross-account access a release gate, and a bypass that
exists in the code is a bypass that can ship.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Session, User
from ..services.auth import SESSION_COOKIE_NAME, AuthError, resolve_session

DbSessionDep = Annotated[DbSession, Depends(get_db)]


def get_session_and_user(
    db: DbSessionDep,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> tuple[Session, User]:
    try:
        return resolve_session(db, session_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


def get_current_user(
    pair: Annotated[tuple[Session, User], Depends(get_session_and_user)],
) -> User:
    _, user = pair
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSession = Annotated[tuple[Session, User], Depends(get_session_and_user)]
