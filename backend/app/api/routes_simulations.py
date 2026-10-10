"""Simulation endpoints (PRD FR10–FR12, AC07).

Stateless by design: a simulation changes nothing until the user
applies the plan, so these are calculators with a database behind them
only for the capacity estimate.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, StrictInt

from ..domain.capacity import MINIMUM_MONTHS
from ..domain.simulation import (
    DayCountBasis,
    SimulationError,
    simulate_deposit,
    simulate_regular_saving,
)
from ..services.capacity import estimate
from .deps import CurrentUser, DbSessionDep
from .schemas import NonNegativeRupiah, PositiveRupiah

router = APIRouter(prefix="/simulations", tags=["simulations"])


class DepositIn(BaseModel):
    principal: PositiveRupiah
    #: A string keeps a quoted rate exact: "4.25" is read as 17/4, not
    #: as the nearest binary value.
    annual_rate_percent: str = Field(examples=["4", "4.25"])
    basis: DayCountBasis = DayCountBasis.MONTHS_12
    months: int | None = Field(default=None, ge=1, le=600)
    days: int | None = Field(default=None, ge=1, le=36500)
    #: None means "not known yet" and marks the result incomplete.
    #: Pass "0" for a confirmed zero.
    tax_percent: str | None = None
    fees: NonNegativeRupiah = 0


class DepositOut(BaseModel):
    principal: StrictInt
    gross_interest: StrictInt
    tax: StrictInt
    fees: StrictInt
    net_interest: StrictInt
    final_value: StrictInt
    year_fraction: str
    basis: str
    #: False when a component was unknown, so the net figure must not be
    #: presented as settled.
    complete: bool
    formula_version: str


class SavingIn(BaseModel):
    target: PositiveRupiah
    initial: NonNegativeRupiah = 0
    periods: int = Field(ge=1, le=600)


class SavingOut(BaseModel):
    target: StrictInt
    initial: StrictInt
    shortfall: StrictInt
    periods: int
    per_period: StrictInt
    total_saved: StrictInt
    overshoot: StrictInt
    formula_version: str


class CapacityOut(BaseModel):
    reliable_income: StrictInt
    cash_expenses: StrictInt
    obligations: StrictInt
    reserves: StrictInt
    gross: StrictInt
    available: StrictInt
    months_observed: int
    reliable: bool
    notes: list[str]


@router.post("/deposit", response_model=DepositOut)
def deposit(body: DepositIn, user: CurrentUser) -> DepositOut:
    """Simple interest on a fixed deposit. Saves nothing (AC07)."""
    try:
        result = simulate_deposit(
            principal=body.principal,
            annual_rate_percent=body.annual_rate_percent,
            basis=body.basis,
            months=body.months,
            days=body.days,
            tax_percent=body.tax_percent,
            fees=body.fees,
        )
    except SimulationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_simulation", "message": str(exc)}
        ) from exc

    return DepositOut(**asdict(result))


@router.post("/saving", response_model=SavingOut)
def saving(body: SavingIn, user: CurrentUser) -> SavingOut:
    """Flat saving toward a target, zero interest (the MVP baseline)."""
    try:
        result = simulate_regular_saving(
            target=body.target, initial=body.initial, periods=body.periods
        )
    except SimulationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_simulation", "message": str(exc)}
        ) from exc

    return SavingOut(**asdict(result))


@router.get("/capacity", response_model=CapacityOut)
def capacity(
    user: CurrentUser,
    db: DbSessionDep,
    months: Annotated[int, Query(ge=1, le=24)] = MINIMUM_MONTHS,
    reserves: Annotated[int, Query(ge=0)] = 0,
) -> CapacityOut:
    """What the user can set aside per month, from their own history."""
    result = estimate(
        db,
        user.id,
        timezone_name=user.timezone,
        months=months,
        reserves=reserves,
        now=datetime.now(timezone.utc),
    )

    return CapacityOut(
        reliable_income=result.inputs.reliable_income,
        cash_expenses=result.inputs.cash_expenses,
        obligations=result.inputs.obligations,
        reserves=result.inputs.reserves,
        gross=result.gross,
        available=result.available,
        months_observed=result.months_observed,
        reliable=result.reliable,
        notes=result.notes,
    )
