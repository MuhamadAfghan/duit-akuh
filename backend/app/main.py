"""FastAPI application.

Every money endpoint goes through ``deps.get_current_user``, which has
no bypass by design (AC08).

The chat orchestrator is wired to the lumi-ai adapter; see
``services/chat/``.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse, RedirectResponse

from .api.routes_accounts import router as accounts_router
from .api.routes_auth import router as auth_router
from .api.routes_budgets import router as budgets_router
from .api.routes_chat import router as chat_router
from .api.routes_export import router as export_router
from .api.routes_goals import router as goals_router
from .api.routes_reports import router as reports_router
from .api.routes_simulations import router as simulations_router
from .api.routes_transactions import router as transactions_router
from .config import get_settings
from .domain.errors import DomainError

settings = get_settings()

app = FastAPI(
    title="lega API",
    version="0.1.0",
    description="Ledger and chat orchestration for a personal finance app.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#: Where a browser that lost its session is sent.
#:
#: Relative on purpose: the browser reached the API through the
#: frontend's own origin (`/srv/*`, rewritten by next.config.mjs), so a
#: relative Location lands on the app rather than on the API host.
SIGN_IN_PATH = "/auth/sign-in"


@app.exception_handler(HTTPException)
async def unauthenticated_handler(request: Request, exc: HTTPException):
    """Send a *browser* to the sign-in page instead of showing it JSON.

    Almost everything here is called by fetch, and a 401 body is exactly
    what that wants. But two things are plain links — the CSV exports —
    because letting the browser handle the download keeps the
    Content-Disposition filename and the session cookie without any
    JavaScript. When the session has expired, those links were
    navigating the whole tab onto an API response, and the person was
    left staring at `{"detail":{"code":"not_authenticated"}}` with the
    app gone and only the back button to save them.

    An HTML `Accept` on a GET is a document navigation; nothing else in
    this API asks for HTML. Every other caller keeps the JSON.
    """
    wants_html = "text/html" in request.headers.get("accept", "")

    if exc.status_code == 401 and request.method == "GET" and wants_html:
        # 303: whatever the original method, follow this with a GET.
        return RedirectResponse(SIGN_IN_PATH, status_code=303)

    return await http_exception_handler(request, exc)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Business-rule violations are 422, not 500.

    They are expected outcomes — an ambiguous account name, an allocation
    that does not fit — and the chat orchestrator turns them into a
    question for the user rather than an error screen. The ``code`` lets
    it branch without parsing prose.
    """
    return JSONResponse(
        status_code=422,
        content={"code": exc.code, "message": str(exc)},
    )


app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(transactions_router)
app.include_router(chat_router)
app.include_router(reports_router)
app.include_router(goals_router)
app.include_router(budgets_router)
app.include_router(simulations_router)
app.include_router(export_router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness only: deliberately does not touch the database.

    A health check that fails on a slow query causes restart loops under
    exactly the load where staying up matters.
    """
    return {"status": "ok", "env": settings.app_env}
