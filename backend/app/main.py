"""FastAPI application.

Every money endpoint goes through ``deps.get_current_user``, which has
no bypass by design (AC08).

Next: the chat orchestrator that calls the lumi-ai service.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from .api.routes_accounts import router as accounts_router
from .api.routes_auth import router as auth_router
from .api.routes_transactions import router as transactions_router
from .config import get_settings
from .domain.errors import DomainError

settings = get_settings()

app = FastAPI(
    title="Duit Akuh API",
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


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness only: deliberately does not touch the database.

    A health check that fails on a slow query causes restart loops under
    exactly the load where staying up matters.
    """
    return {"status": "ok", "env": settings.app_env}
