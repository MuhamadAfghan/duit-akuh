"""FastAPI application.

Deliberately small right now. The ledger foundation is in place, but the
HTTP surface stays minimal until authentication exists: the PRD makes
per-owner authorization a release gate (AC08), so adding endpoints that
read or write money before there is a real user identity would mean
shipping an unauthenticated financial API, even briefly.

Next: email/password auth, then account and transaction endpoints, then
the chat orchestrator that calls the lumi-ai service.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

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


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness only: deliberately does not touch the database.

    A health check that fails on a slow query causes restart loops under
    exactly the load where staying up matters.
    """
    return {"status": "ok", "env": settings.app_env}
