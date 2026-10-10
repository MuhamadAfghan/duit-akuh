"""Goals and allocations (PRD FR07)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select

from ..domain.errors import AllocationExceedsBalance, DomainError
from ..domain.goals import plan_against_capacity
from ..models import Goal
from ..services import goals as goals_service
from .deps import CurrentUser, DbSessionDep
from .schemas import PositiveRupiah

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: PositiveRupiah
    target_date: datetime | None = None
    priority: int = Field(default=0, ge=0, le=100)


class AllocationIn(BaseModel):
    account_id: uuid.UUID
    amount: PositiveRupiah


class MoveAllocationIn(BaseModel):
    account_id: uuid.UUID
    to_goal_id: uuid.UUID
    amount: PositiveRupiah


class AllocationOut(BaseModel):
    account_id: uuid.UUID
    amount: StrictInt


class GoalOut(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: StrictInt
    target_date: datetime | None
    priority: int
    status: str
    saved: StrictInt
    shortfall: StrictInt
    percent: StrictInt
    #: Excess beyond the target, kept out of `percent` so a progress bar
    #: never reads past full.
    surplus: StrictInt
    #: None when no deposit dates remain — there is nothing to divide by.
    per_deposit: StrictInt | None
    allocations: list[AllocationOut]


class AlternativeOut(BaseModel):
    kind: str
    label: str
    value: StrictInt


class PlanOut(BaseModel):
    goal_id: uuid.UUID
    capacity: StrictInt
    required_per_deposit: StrictInt | None
    feasible: bool
    alternatives: list[AlternativeOut]


def _domain_error(exc: DomainError) -> HTTPException:
    code = getattr(exc, "code", "domain_error")
    http_status = 404 if code in {"goal_not_found", "allocation_not_found"} else 422
    return HTTPException(status_code=http_status, detail={"code": code, "message": str(exc)})


def _to_out(db, user_id, goal: Goal, remaining_deposits: int = 0) -> GoalOut:
    view = goals_service.goal_view(db, user_id, goal.id, remaining_deposits=remaining_deposits)

    return GoalOut(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        target_date=goal.target_date,
        priority=goal.priority,
        status=view.progress.status.value,
        saved=view.progress.saved,
        shortfall=view.progress.shortfall,
        percent=view.progress.percent,
        surplus=view.progress.surplus,
        per_deposit=view.progress.per_deposit,
        allocations=[
            AllocationOut(account_id=a.account_id, amount=a.amount) for a in view.allocations
        ],
    )


@router.get("", response_model=list[GoalOut])
def list_goals(
    user: CurrentUser,
    db: DbSessionDep,
    remaining_deposits: Annotated[int, Query(ge=0, le=600)] = 0,
) -> list[GoalOut]:
    rows = db.scalars(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.priority, Goal.name)
    ).all()

    return [_to_out(db, user.id, goal, remaining_deposits) for goal in rows]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=GoalOut)
def create_goal(body: GoalCreateIn, user: CurrentUser, db: DbSessionDep) -> GoalOut:
    goal = goals_service.create_goal(
        db,
        user_id=user.id,
        name=body.name,
        target_amount=body.target_amount,
        target_date=body.target_date,
        priority=body.priority,
    )

    return _to_out(db, user.id, goal)


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(
    goal_id: uuid.UUID,
    user: CurrentUser,
    db: DbSessionDep,
    remaining_deposits: Annotated[int, Query(ge=0, le=600)] = 0,
) -> GoalOut:
    try:
        view = goals_service.goal_view(db, user.id, goal_id, remaining_deposits=remaining_deposits)
    except DomainError as exc:
        raise _domain_error(exc) from exc

    return _to_out(db, user.id, view.goal, remaining_deposits)


@router.post("/{goal_id}/allocations", response_model=GoalOut)
def set_allocation(
    goal_id: uuid.UUID, body: AllocationIn, user: CurrentUser, db: DbSessionDep
) -> GoalOut:
    """Earmark part of an account for this goal.

    Replaces any existing earmark for the same account, so repeating the
    call is not cumulative. Moves no money (AC05).
    """
    try:
        goals_service.allocate(
            db,
            user_id=user.id,
            goal_id=goal_id,
            account_id=body.account_id,
            amount=body.amount,
        )
    except AllocationExceedsBalance as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except DomainError as exc:
        raise _domain_error(exc) from exc

    goal = db.get(Goal, goal_id)

    return _to_out(db, user.id, goal)


@router.post("/{goal_id}/allocations/release", status_code=status.HTTP_204_NO_CONTENT)
def release_allocation(
    goal_id: uuid.UUID,
    account_id: Annotated[uuid.UUID, Query()],
    user: CurrentUser,
    db: DbSessionDep,
) -> None:
    try:
        goals_service.release(db, user_id=user.id, goal_id=goal_id, account_id=account_id)
    except DomainError as exc:
        raise _domain_error(exc) from exc


@router.post("/{goal_id}/allocations/move", status_code=status.HTTP_204_NO_CONTENT)
def move_allocation(
    goal_id: uuid.UUID, body: MoveAllocationIn, user: CurrentUser, db: DbSessionDep
) -> None:
    """Move an earmark to another goal. Not a transfer; no money moves."""
    try:
        goals_service.move_between_goals(
            db,
            user_id=user.id,
            account_id=body.account_id,
            from_goal_id=goal_id,
            to_goal_id=body.to_goal_id,
            amount=body.amount,
        )
    except DomainError as exc:
        raise _domain_error(exc) from exc


@router.get("/{goal_id}/plan", response_model=PlanOut)
def plan(
    goal_id: uuid.UUID,
    user: CurrentUser,
    db: DbSessionDep,
    capacity: Annotated[int, Query(ge=0)],
    remaining_deposits: Annotated[int, Query(ge=1, le=600)],
) -> PlanOut:
    """Check a goal against what the user can actually set aside (FR11)."""
    try:
        view = goals_service.goal_view(db, user.id, goal_id, remaining_deposits=remaining_deposits)
    except DomainError as exc:
        raise _domain_error(exc) from exc

    result = plan_against_capacity(view.progress, capacity=capacity)

    return PlanOut(
        goal_id=goal_id,
        capacity=result.capacity,
        required_per_deposit=view.progress.per_deposit,
        feasible=result.feasible,
        alternatives=[
            AlternativeOut(kind=a.kind, label=a.label, value=a.value) for a in result.alternatives
        ],
    )
