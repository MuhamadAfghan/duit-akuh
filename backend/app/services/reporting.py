"""Spending and income over a period, broken down by category (FR06).

Three properties matter here, and all three fall out of the double-entry
model rather than being special-cased:

* **Transfers never appear.** They touch only asset accounts, so a query
  restricted to expense accounts cannot see them (AC02).
* **Credit-card payments never appear.** They debit a liability, not an
  expense, so paying a bill does not look like new spending (AC03).
* **Refunds reduce their category.** A refund credits the expense
  account, so summing that account's entries nets it off automatically.

The only real work is the date range, which has to be computed in the
user's timezone — see :mod:`app.domain.periods`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..domain.periods import Period
from ..models import Account, AccountKind, Entry, Transaction, TransactionStatus


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    name: str
    amount: int


@dataclass(frozen=True, slots=True)
class PeriodReport:
    label: str
    start: str
    end: str
    expense_total: int
    income_total: int
    categories: list[CategoryTotal]
    transaction_count: int


def _totals_by_category(
    db: DbSession, user_id: uuid.UUID, period: Period, kind: AccountKind
) -> list[tuple[str, int]]:
    rows = db.execute(
        select(Account.name, func.coalesce(func.sum(Entry.amount), 0))
        .join(Entry, Entry.account_id == Account.id)
        .join(Transaction, Transaction.id == Entry.transaction_id)
        .where(
            Entry.user_id == user_id,
            Account.kind == kind,
            Transaction.occurred_at >= period.start,
            Transaction.occurred_at < period.end,
            # A reversed transaction keeps its rows for the audit trail,
            # but its reversal cancels it out. Both are left in so the
            # arithmetic nets to zero on its own; excluding only one side
            # would double-count the correction.
            Transaction.status.in_([TransactionStatus.POSTED, TransactionStatus.REVERSED]),
        )
        .group_by(Account.name)
        .order_by(func.sum(Entry.amount).desc())
    ).all()

    return [(name, int(total)) for name, total in rows]


def period_report(db: DbSession, user_id: uuid.UUID, period: Period) -> PeriodReport:
    """Spending and income within ``period``, with a category breakdown."""
    expenses = _totals_by_category(db, user_id, period, AccountKind.EXPENSE)
    incomes = _totals_by_category(db, user_id, period, AccountKind.INCOME)

    count = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_at >= period.start,
            Transaction.occurred_at < period.end,
        )
    )

    return PeriodReport(
        label=period.label,
        start=period.start.isoformat(),
        end=period.end.isoformat(),
        expense_total=sum(amount for _, amount in expenses),
        # Income accounts carry credit (negative) balances, so negate to
        # read naturally.
        income_total=-sum(amount for _, amount in incomes),
        categories=[
            # A category that netted to zero (fully refunded) is dropped:
            # listing "Belanja Rp0" is noise, not information.
            CategoryTotal(name=name, amount=amount)
            for name, amount in expenses
            if amount != 0
        ],
        transaction_count=int(count or 0),
    )


def category_total_for_period(
    db: DbSession, user_id: uuid.UUID, period: Period, category: str
) -> int | None:
    """Total for one expense category, or None when no such category exists.

    None rather than 0 so the caller can tell "you have not used that
    category" from "you spent nothing on it this month" — the PRD is
    clear that an unknown reference should prompt a question, not an
    answer that looks authoritative.
    """
    needle = category.strip().lower()

    account = db.scalar(
        select(Account).where(
            Account.user_id == user_id,
            Account.kind == AccountKind.EXPENSE,
            func.lower(Account.name) == needle,
        )
    )

    if account is None:
        return None

    total = db.scalar(
        select(func.coalesce(func.sum(Entry.amount), 0))
        .join(Transaction, Transaction.id == Entry.transaction_id)
        .where(
            Entry.user_id == user_id,
            Entry.account_id == account.id,
            Transaction.occurred_at >= period.start,
            Transaction.occurred_at < period.end,
        )
    )

    return int(total or 0)


def known_expense_categories(db: DbSession, user_id: uuid.UUID) -> list[str]:
    """Names of the user's expense categories, for disambiguation."""
    return list(
        db.scalars(
            select(Account.name)
            .where(Account.user_id == user_id, Account.kind == AccountKind.EXPENSE)
            .order_by(Account.name)
        ).all()
    )
