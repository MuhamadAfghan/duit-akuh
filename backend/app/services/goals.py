"""Creating goals and moving allocations (PRD FR07).

An allocation is an earmark on money already in an account. It writes no
ledger entry, so it cannot change net assets — that is AC05, and it holds
structurally rather than by a check somewhere.

What does need checking is over-promising: the total earmarked on an
account may not exceed its positive balance, and moving an earmark
between goals is not a transfer and must not look like one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..domain.allocations import AllocationSnapshot, check_allocation_fits
from ..domain.errors import AllocationExceedsBalance, DomainError
from ..domain.goals import GoalProgress, GoalStatus, goal_progress
from ..models import Account, AccountKind, Allocation, AuditEvent, Goal, new_uuid
from ..money import positive_rupiah
from .posting import account_balance


class GoalNotFound(DomainError):
    code = "goal_not_found"


class AllocationNotFound(DomainError):
    code = "allocation_not_found"


class InvalidGoal(DomainError):
    code = "invalid_goal"


@dataclass(frozen=True, slots=True)
class GoalView:
    goal: Goal
    progress: GoalProgress
    allocations: list[Allocation]


def _snapshots(db: DbSession, user_id: uuid.UUID) -> list[AllocationSnapshot]:
    rows = db.scalars(select(Allocation).where(Allocation.user_id == user_id)).all()
    return [
        AllocationSnapshot(account_id=a.account_id, goal_id=a.goal_id, amount=a.amount)
        for a in rows
    ]


def _owned_goal(db: DbSession, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id))

    if goal is None:
        raise GoalNotFound("Target tidak ditemukan")

    return goal


def _owned_account(db: DbSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    account = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == user_id))

    if account is None:
        raise GoalNotFound("Kantong tidak ditemukan")

    if account.kind is not AccountKind.ASSET:
        # Earmarking a liability or a category is meaningless: there is
        # no balance there to set aside.
        raise InvalidGoal(f"'{account.name}' bukan kantong yang bisa dialokasikan")

    return account


def create_goal(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    name: str,
    target_amount: int,
    target_date: datetime | None = None,
    priority: int = 0,
) -> Goal:
    goal = Goal(
        id=new_uuid(),
        user_id=user_id,
        name=name.strip(),
        target_amount=positive_rupiah(target_amount),
        target_date=target_date,
        priority=priority,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal)
    db.flush()

    db.add(
        AuditEvent(
            user_id=user_id,
            action="goal.created",
            object_type="goal",
            object_id=goal.id,
            after={"name": goal.name, "target_amount": goal.target_amount},
        )
    )
    db.flush()

    return goal


def saved_for(db: DbSession, user_id: uuid.UUID, goal_id: uuid.UUID) -> int:
    """Total currently earmarked for a goal, across all accounts."""
    return sum(
        a.amount
        for a in db.scalars(
            select(Allocation).where(Allocation.user_id == user_id, Allocation.goal_id == goal_id)
        ).all()
    )


def goal_view(
    db: DbSession, user_id: uuid.UUID, goal_id: uuid.UUID, *, remaining_deposits: int = 0
) -> GoalView:
    goal = _owned_goal(db, user_id, goal_id)

    allocations = list(
        db.scalars(
            select(Allocation).where(Allocation.user_id == user_id, Allocation.goal_id == goal_id)
        ).all()
    )

    progress = goal_progress(
        target=goal.target_amount,
        saved=sum(a.amount for a in allocations),
        remaining_deposits=remaining_deposits,
        status=GoalStatus(goal.status),
    )

    return GoalView(goal=goal, progress=progress, allocations=allocations)


def allocate(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    account_id: uuid.UUID,
    amount: int,
) -> Allocation:
    """Earmark part of an account's balance for a goal.

    Replaces any existing earmark for the same goal/account pair rather
    than adding to it, so repeating the request is not cumulative.
    """
    amount = positive_rupiah(amount)
    goal = _owned_goal(db, user_id, goal_id)
    account = _owned_account(db, user_id, account_id)

    balance = account_balance(db, user_id, account_id)

    check_allocation_fits(
        account_id=account_id,
        account_balance=balance,
        existing=_snapshots(db, user_id),
        new_amount=amount,
        replacing_goal_id=goal_id,
    )

    existing = db.scalar(
        select(Allocation).where(
            Allocation.user_id == user_id,
            Allocation.goal_id == goal_id,
            Allocation.account_id == account_id,
        )
    )

    before = existing.amount if existing else None

    if existing is None:
        existing = Allocation(
            id=new_uuid(),
            user_id=user_id,
            goal_id=goal_id,
            account_id=account_id,
            amount=amount,
        )
        db.add(existing)
    else:
        existing.amount = amount
        existing.version += 1

    db.add(
        AuditEvent(
            user_id=user_id,
            action="allocation.set",
            object_type="allocation",
            object_id=existing.id,
            before={"amount": before} if before is not None else None,
            after={
                "amount": amount,
                "goal": goal.name,
                "account": account.name,
            },
        )
    )
    db.flush()

    return existing


def release(
    db: DbSession, *, user_id: uuid.UUID, goal_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    """Drop an earmark. Moves no money — the balance was never touched."""
    allocation = db.scalar(
        select(Allocation).where(
            Allocation.user_id == user_id,
            Allocation.goal_id == goal_id,
            Allocation.account_id == account_id,
        )
    )

    if allocation is None:
        raise AllocationNotFound("Alokasi tidak ditemukan")

    db.add(
        AuditEvent(
            user_id=user_id,
            action="allocation.released",
            object_type="allocation",
            object_id=allocation.id,
            before={"amount": allocation.amount},
        )
    )
    db.delete(allocation)
    db.flush()


def move_between_goals(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    from_goal_id: uuid.UUID,
    to_goal_id: uuid.UUID,
    amount: int,
) -> None:
    """Move an earmark from one goal to another on the same account.

    Explicitly **not** a transfer: no money moves, no ledger entry is
    written, and net assets are unchanged. The PRD calls this out because
    presenting it as a transfer would be misleading.
    """
    amount = positive_rupiah(amount)

    if from_goal_id == to_goal_id:
        raise InvalidGoal("Target asal dan tujuan tidak boleh sama")

    source = db.scalar(
        select(Allocation).where(
            Allocation.user_id == user_id,
            Allocation.goal_id == from_goal_id,
            Allocation.account_id == account_id,
        )
    )

    if source is None or source.amount < amount:
        raise AllocationNotFound("Alokasi asal tidak cukup untuk dipindahkan")

    target = db.scalar(
        select(Allocation).where(
            Allocation.user_id == user_id,
            Allocation.goal_id == to_goal_id,
            Allocation.account_id == account_id,
        )
    )

    _owned_goal(db, user_id, to_goal_id)

    source.amount -= amount
    source.version += 1

    if source.amount == 0:
        db.delete(source)

    if target is None:
        db.add(
            Allocation(
                id=new_uuid(),
                user_id=user_id,
                goal_id=to_goal_id,
                account_id=account_id,
                amount=amount,
            )
        )
    else:
        target.amount += amount
        target.version += 1

    db.add(
        AuditEvent(
            user_id=user_id,
            action="allocation.moved",
            object_type="allocation",
            object_id=account_id,
            after={
                "from_goal": str(from_goal_id),
                "to_goal": str(to_goal_id),
                "amount": amount,
            },
        )
    )
    db.flush()


def allocated_on_account(db: DbSession, user_id: uuid.UUID, account_id: uuid.UUID) -> int:
    return sum(
        a.amount
        for a in db.scalars(
            select(Allocation).where(
                Allocation.user_id == user_id, Allocation.account_id == account_id
            )
        ).all()
    )


def headroom(db: DbSession, user_id: uuid.UUID, account_id: uuid.UUID) -> int:
    """How much of an account is still free to earmark."""
    balance = max(0, account_balance(db, user_id, account_id))
    return max(0, balance - allocated_on_account(db, user_id, account_id))


__all__ = [
    "AllocationExceedsBalance",
    "AllocationNotFound",
    "GoalNotFound",
    "GoalView",
    "InvalidGoal",
    "allocate",
    "allocated_on_account",
    "create_goal",
    "goal_view",
    "headroom",
    "move_between_goals",
    "release",
    "saved_for",
]
