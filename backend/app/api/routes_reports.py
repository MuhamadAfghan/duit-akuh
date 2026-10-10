"""Spending reports over a period (PRD FR06)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, StrictInt

from ..domain.periods import PERIOD_KEYWORDS, PeriodError, resolve_period
from ..services.reporting import period_report
from .deps import CurrentUser, DbSessionDep

router = APIRouter(prefix="/reports", tags=["reports"])


class CategoryOut(BaseModel):
    name: str
    amount: StrictInt


class PeriodReportOut(BaseModel):
    label: str
    start: str
    end: str
    expense_total: StrictInt
    income_total: StrictInt
    categories: list[CategoryOut]
    transaction_count: StrictInt


@router.get("/spending", response_model=PeriodReportOut)
def spending(
    user: CurrentUser,
    db: DbSessionDep,
    period: Annotated[
        str, Query(description=f"One of: {', '.join(PERIOD_KEYWORDS)}")
    ] = "bulan_ini",
    start: Annotated[date | None, Query(description="Inclusive local start date")] = None,
    end: Annotated[date | None, Query(description="Inclusive local end date")] = None,
) -> PeriodReportOut:
    """Spending and income for a period, broken down by category.

    Balances are deliberately not here: a balance is a point in time, not
    a range, and putting the two in one response invites reading a
    month's spending as if it were a balance.
    """
    try:
        resolved = resolve_period(
            period,
            now=datetime.now(timezone.utc),
            timezone_name=user.timezone,
            start=start,
            end=end,
        )
    except PeriodError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_period", "message": str(exc)}
        ) from exc

    report = period_report(db, user.id, resolved)

    return PeriodReportOut(
        label=report.label,
        start=report.start,
        end=report.end,
        expense_total=report.expense_total,
        income_total=report.income_total,
        categories=[CategoryOut(name=c.name, amount=c.amount) for c in report.categories],
        transaction_count=report.transaction_count,
    )
