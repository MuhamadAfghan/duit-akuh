"""Authentication endpoints.

The session token is delivered **only** as an httpOnly cookie and never
in a response body, so the PWA's JavaScript never holds a credential —
the same principle as AC21, which forbids secrets reaching the client.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from .. import emails
from ..config import get_settings
from ..models import User
from ..services import auth as auth_service
from ..services import mail as mail_service
from ..services import password_reset
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


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=512)
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
    status_code = code_map.get(type(exc), status.HTTP_400_BAD_REQUEST)

    # A 429 that does not say when to come back leaves the client
    # guessing, and guessing means retrying too early.
    headers = (
        {"Retry-After": str(int(auth_service.LOGIN_WINDOW.total_seconds()))}
        if status_code == status.HTTP_429_TOO_MANY_REQUESTS
        else None
    )

    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
        headers=headers,
    )


def _queue_password_changed_email(tasks: BackgroundTasks, user, *, now: datetime) -> None:
    """Tell the account holder their password moved.

    Sent on every change, reset or deliberate, because the whole value
    of the notice is that a change nobody made shows up somewhere the
    attacker does not control.
    """
    settings = get_settings()

    message = emails.render(
        "password_changed",
        email=user.email,
        changed_at=emails.format_when(now, user.timezone),
        forgot_url=f"{settings.app_base_url}/auth/lupa",
        mail_from=settings.mail_from or "",
    )

    tasks.add_task(mail_service.send_quietly, to=user.email, email=message)


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
    tasks: BackgroundTasks,
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

    _queue_password_changed_email(tasks, user, now=datetime.now(timezone.utc))
    _clear_session_cookie(response)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ForgotPasswordIn, db: DbSessionDep, tasks: BackgroundTasks) -> Response:
    """Ask for a reset link.

    Answers 202 for every address, registered or not. Saying "no such
    account" here would turn this endpoint into a way to find out who
    banks with us, which is exactly the enumeration the sign-in error
    message already refuses to allow.

    The send runs after the response for the same reason: how long SMTP
    takes must not become a signal about whether there was anything to
    send.
    """
    now = datetime.now(timezone.utc)

    try:
        row, raw_token = password_reset.request_reset(db, email=body.email, now=now)
    except password_reset.TooManyRequests as exc:
        # The rows this handler counts were written by earlier requests
        # and are already committed; nothing is pending here. The commit
        # is kept for the same reason as in login(): if anything is ever
        # added above this line, its write must survive the raise.
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": exc.code, "message": str(exc)},
            headers={"Retry-After": str(int(password_reset.REQUEST_WINDOW.total_seconds()))},
        ) from exc

    if raw_token is not None:
        settings = get_settings()
        owner = db.get(User, row.user_id)

        message = emails.render(
            "reset_password",
            email=row.email,
            requested_at=emails.format_when(now, owner.timezone if owner else None),
            reset_url=f"{settings.app_base_url}/auth/reset?token={raw_token}",
            expires_minutes=str(int(password_reset.TOKEN_LIFETIME.total_seconds() // 60)),
            mail_from=settings.mail_from or "",
        )

        tasks.add_task(mail_service.send_quietly, to=row.email, email=message)

    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    body: ResetPasswordIn, db: DbSessionDep, response: Response, tasks: BackgroundTasks
) -> Response:
    """Spend a reset token and set a new password.

    No session cookie is issued. Every session was just revoked, so
    handing back a fresh one here would quietly undo the one guarantee
    a reset is supposed to make.
    """
    now = datetime.now(timezone.utc)

    try:
        user = password_reset.consume_token(
            db, raw_token=body.token, new_password=body.new_password, now=now
        )
    except password_reset.InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except auth_service.AuthError as exc:
        raise _auth_http_error(exc) from exc

    _queue_password_changed_email(tasks, user, now=now)
    _clear_session_cookie(response)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
