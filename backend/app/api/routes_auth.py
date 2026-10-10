"""Authentication endpoints.

The session token is delivered **only** as an httpOnly cookie and never
in a response body, so the PWA's JavaScript never holds a credential —
the same principle as AC21, which forbids secrets reaching the client.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..services import auth as auth_service
from .deps import CurrentSession, CurrentUser, DbSessionDep

router = APIRouter(prefix="/auth", tags=["auth"])


class CredentialsIn(BaseModel):
    email: EmailStr
    # Bounded so an enormous value cannot make the server do expensive
    # hashing work; the service enforces the same limits.
    password: str = Field(
        min_length=auth_service.MIN_PASSWORD_LENGTH,
        max_length=auth_service.MAX_PASSWORD_LENGTH,
    )


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=auth_service.MAX_PASSWORD_LENGTH)
    new_password: str = Field(
        min_length=auth_service.MIN_PASSWORD_LENGTH,
        max_length=auth_service.MAX_PASSWORD_LENGTH,
    )


class UserOut(BaseModel):
    id: str
    email: str
    timezone: str


def _set_session_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()

    response.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=int(auth_service.SESSION_LIFETIME.total_seconds()),
        # Not readable by page scripts, so an XSS bug cannot steal the login.
        httponly=True,
        # Lax rather than Strict: the cookie must survive following a link
        # back into the installed PWA, while still not riding along on a
        # cross-site POST.
        samesite="lax",
        # Only relaxed in development, where the API is served over plain
        # HTTP on localhost.
        secure=settings.is_production,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
        path="/",
    )


def _auth_http_error(exc: auth_service.AuthError) -> HTTPException:
    code_map = {
        auth_service.InvalidCredentials: status.HTTP_401_UNAUTHORIZED,
        auth_service.NotAuthenticated: status.HTTP_401_UNAUTHORIZED,
        auth_service.TooManyAttempts: status.HTTP_429_TOO_MANY_REQUESTS,
        auth_service.EmailAlreadyRegistered: status.HTTP_409_CONFLICT,
        auth_service.WeakPassword: status.HTTP_422_UNPROCESSABLE_CONTENT,
    }
    return HTTPException(
        status_code=code_map.get(type(exc), status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def register(
    body: CredentialsIn, db: DbSessionDep, request: Request, response: Response
) -> UserOut:
    """Create an account and sign in immediately."""
    try:
        user = auth_service.register_user(db, email=body.email, password=body.password)
    except auth_service.AuthError as exc:
        raise _auth_http_error(exc) from exc

    _, raw_token = auth_service.create_session(
        db, user=user, user_agent=request.headers.get("user-agent")
    )
    _set_session_cookie(response, raw_token)

    return UserOut(id=str(user.id), email=user.email, timezone=user.timezone)


@router.post("/login", response_model=UserOut)
def login(body: CredentialsIn, db: DbSessionDep, request: Request, response: Response) -> UserOut:
    try:
        user = auth_service.authenticate(db, email=body.email, password=body.password)
    except auth_service.AuthError as exc:
        # The failed attempt was written to this session, and the request
        # is about to raise - which makes get_db roll back. Without this
        # commit the throttle counter silently never increments and the
        # lockout required by PRD section 9 does nothing at all.
        #
        # Safe because a failed sign-in has nothing else pending in the
        # session. Anything added to this handler before authenticate()
        # would also be committed here.
        db.commit()
        raise _auth_http_error(exc) from exc

    _, raw_token = auth_service.create_session(
        db, user=user, user_agent=request.headers.get("user-agent")
    )
    _set_session_cookie(response, raw_token)

    return UserOut(id=str(user.id), email=user.email, timezone=user.timezone)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(pair: CurrentSession, db: DbSessionDep, response: Response) -> Response:
    session, _ = pair
    auth_service.revoke_session(db, session)
    _clear_session_cookie(response)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, timezone=user.timezone)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordIn,
    user: CurrentUser,
    db: DbSessionDep,
    response: Response,
) -> Response:
    """Change the password, which signs out every session including this one."""
    try:
        auth_service.change_password(
            db,
            user=user,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except auth_service.AuthError as exc:
        raise _auth_http_error(exc) from exc

    _clear_session_cookie(response)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
