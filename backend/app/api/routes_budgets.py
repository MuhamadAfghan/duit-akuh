"""Budgets (PRD FR08)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, StrictInt

from ..domain.errors import DomainError
from ..domain.periods import PERIOD_KEYWORDS, PeriodError, resolve_period
from ..services import budgets as budgets_service
from .deps import CurrentUser, DbSessionDep
from .schemas import PositiveRupiah

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetIn(BaseModel):
    category: str = Field(min_length=1, max_length=120)
    amount: PositiveRupiah


class BudgetStatusOut(BaseModel):
    category: str
    limit: StrictInt
    spent: StrictInt
    #: Negative when overspent - clamping it would hide the one thing a
    #: budget exists to show.
    remaining: StrictInt
    #: Uncapped: 130 means 30% over.
    percent: StrictInt
    state: str


class BudgetReportOut(BaseModel):
    label: str
    budgets: list[BudgetStatusOut]
    total_limit: StrictInt
    total_spent: StrictInt
    total_remaining: StrictInt
    exceeded: list[str]
    approaching: list[str]


def _resolve(user, period: str):
    try:
        return resolve_period(period, now=datetime.now(timezone.utc), timezone_name=user.timezone)
    except PeriodError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_period", "message": str(exc)}
        ) from exc


def _to_out(report) -> BudgetReportOut:
    return BudgetReportOut(
        label=report.label,
        budgets=[
            BudgetStatusOut(
                category=s.category,
                limit=s.limit,
                spent=s.spent,
                remaining=s.remaining,
                percent=s.percent,
                state=s.state.value,
            )
            for s in report.statuses
        ],
        total_limit=report.summary.total_limit,
        total_spent=report.summary.total_spent,
        total_remaining=report.summary.total_remaining,
        exceeded=report.summary.exceeded,
        approaching=report.summary.approaching,
    )


@router.get("", response_model=BudgetReportOut)
def list_budgets(
    user: CurrentUser,
    db: DbSessionDep,
    period: Annotated[
        str, Query(description=f"One of: {', '.join(PERIOD_KEYWORDS)}")
    ] = "bulan_ini",
) -> BudgetReportOut:
    """Budgets with what has been spent against them in the period."""
    return _to_out(budgets_service.report(db, user.id, _resolve(user, period)))


@router.put("", response_model=BudgetReportOut)
def set_budget(body: BudgetIn, user: CurrentUser, db: DbSessionDep) -> BudgetReportOut:
    """Set the monthly limit for a category. Idempotent by category."""
    try:
        budgets_service.set_budget(db, user_id=user.id, category=body.category, amount=body.amount)
    except DomainError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": getattr(exc, "code", "invalid_budget"), "message": str(exc)},
        ) from exc

    return _to_out(budgets_service.report(db, user.id, _resolve(user, "bulan_ini")))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_budget(
    category: Annotated[str, Query(min_length=1)], user: CurrentUser, db: DbSessionDep
) -> None:
    try:
        budgets_service.remove_budget(db, user_id=user.id, category=category)
    except budgets_service.BudgetNotFound as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "message": str(exc)}
        ) from exc
