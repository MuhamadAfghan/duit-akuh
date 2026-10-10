"""Setting and evaluating budgets (PRD FR08)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..domain.budgets import BudgetStatus, BudgetSummary, evaluate, summarise
from ..domain.errors import DomainError
from ..domain.periods import Period
from ..models import Account, AccountKind, AuditEvent, Budget, Entry, Transaction, new_uuid
from ..money import positive_rupiah


class BudgetNotFound(DomainError):
    code = "budget_not_found"


class InvalidBudget(DomainError):
    code = "invalid_budget"


@dataclass(frozen=True, slots=True)
class BudgetReport:
    label: str
    statuses: list[BudgetStatus]
    summary: BudgetSummary


def _expense_account(db: DbSession, user_id: uuid.UUID, category: str) -> Account:
    """Find an expense category by name, creating it if new.

    Budgeting for a category before spending in it is normal - "I want to
    keep transport under 500k" comes before the first trip - so a missing
    category is created rather than refused.
    """
    needle = category.strip()

    if not needle:
        raise InvalidBudget("Nama kategori tidak boleh kosong")

    account = db.scalar(
        select(Account).where(
            Account.user_id == user_id,
            Account.kind == AccountKind.EXPENSE,
            func.lower(Account.name) == needle.lower(),
        )
    )

    if account is not None:
        return account

    from .accounts import expense_category

    return expense_category(db, user_id, needle)


def set_budget(db: DbSession, *, user_id: uuid.UUID, category: str, amount: int) -> Budget:
    """Create or update the monthly limit for a category."""
    amount = positive_rupiah(amount)
    account = _expense_account(db, user_id, category)

    budget = db.scalar(
        select(Budget).where(Budget.user_id == user_id, Budget.category_account_id == account.id)
    )

    before = budget.amount if budget else None

    if budget is None:
        budget = Budget(
            id=new_uuid(),
            user_id=user_id,
            category_account_id=account.id,
            amount=amount,
        )
        db.add(budget)
    else:
        budget.amount = amount
        budget.is_active = True
        budget.version += 1

    db.add(
        AuditEvent(
            user_id=user_id,
            action="budget.set",
            object_type="budget",
            object_id=budget.id,
            before={"amount": before} if before is not None else None,
            after={"category": account.name, "amount": amount},
        )
    )
    db.flush()

    return budget


def remove_budget(db: DbSession, *, user_id: uuid.UUID, category: str) -> None:
    account = db.scalar(
        select(Account).where(
            Account.user_id == user_id,
            Account.kind == AccountKind.EXPENSE,
            func.lower(Account.name) == category.strip().lower(),
        )
    )

    budget = (
        db.scalar(
            select(Budget).where(
                Budget.user_id == user_id, Budget.category_account_id == account.id
            )
        )
        if account
        else None
    )

    if budget is None:
        raise BudgetNotFound(f"Belum ada budget untuk '{category}'")

    db.add(
        AuditEvent(
            user_id=user_id,
            action="budget.removed",
            object_type="budget",
            object_id=budget.id,
            before={"amount": budget.amount},
        )
    )
    db.delete(budget)
    db.flush()


def _spent_per_category(db: DbSession, user_id: uuid.UUID, period: Period) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(Entry.account_id, func.coalesce(func.sum(Entry.amount), 0))
        .join(Transaction, Transaction.id == Entry.transaction_id)
        .where(
            Entry.user_id == user_id,
            Transaction.occurred_at >= period.start,
            Transaction.occurred_at < period.end,
        )
        .group_by(Entry.account_id)
    ).all()

    return {account_id: int(total) for account_id, total in rows}


def report(db: DbSession, user_id: uuid.UUID, period: Period) -> BudgetReport:
    """Every active budget, with what has been spent against it."""
    rows = db.execute(
        select(Budget, Account.name)
        .join(Account, Account.id == Budget.category_account_id)
        .where(Budget.user_id == user_id, Budget.is_active.is_(True))
        .order_by(Account.name)
    ).all()

    spent = _spent_per_category(db, user_id, period)

    statuses = [
        evaluate(
            category=name,
            limit=budget.amount,
            spent=spent.get(budget.category_account_id, 0),
        )
        for budget, name in rows
    ]

    return BudgetReport(label=period.label, statuses=statuses, summary=summarise(statuses))
