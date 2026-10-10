"""Deriving saving capacity from the ledger (PRD FR10)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..domain.capacity import MINIMUM_MONTHS, Capacity, CapacityInputs, compute_capacity
from ..domain.periods import get_zone, month_period
from ..models import Account, AccountKind, Entry, Transaction, TransactionType


def _months_back(now: datetime, zone, count: int):
    """The last `count` whole calendar months, excluding the current one.

    The current month is partial, and averaging a half-finished month
    with complete ones understates spending.
    """
    today = now.astimezone(zone).date()
    year, month = today.year, today.month
    periods = []

    for _ in range(count):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        periods.append(month_period(year, month, zone))

    return list(reversed(periods))


def _sum_entries(db: DbSession, user_id: uuid.UUID, kind: AccountKind, start, end) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(Entry.amount), 0))
        .join(Account, Account.id == Entry.account_id)
        .join(Transaction, Transaction.id == Entry.transaction_id)
        .where(
            Entry.user_id == user_id,
            Account.kind == kind,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )
    )
    return int(total or 0)


def _sum_card_payments(db: DbSession, user_id: uuid.UUID, start, end) -> int:
    """Card bills actually paid in the window.

    Counted here, at the payment date, because this is a cash-flow
    projection. The purchases that formed the bill are excluded from
    `cash_expenses` below for the same reason - counting both would
    subtract the same money twice.
    """
    total = db.scalar(
        select(func.coalesce(func.sum(Entry.amount), 0))
        .join(Account, Account.id == Entry.account_id)
        .join(Transaction, Transaction.id == Entry.transaction_id)
        .where(
            Entry.user_id == user_id,
            Account.kind == AccountKind.LIABILITY,
            Transaction.type == TransactionType.CARD_PAYMENT,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )
    )
    return int(total or 0)


def _sum_cash_expenses(db: DbSession, user_id: uuid.UUID, start, end) -> int:
    """Expenses paid from asset accounts, excluding anything on credit.

    An expense leg credits its source. Restricting to asset sources
    leaves out card purchases, which are picked up later as the bill.
    """
    total = db.scalar(
        select(func.coalesce(func.sum(-Entry.amount), 0))
        .join(Account, Account.id == Entry.account_id)
        .join(Transaction, Transaction.id == Entry.transaction_id)
        .where(
            Entry.user_id == user_id,
            Account.kind == AccountKind.ASSET,
            Entry.amount < 0,
            Transaction.type.in_([TransactionType.EXPENSE, TransactionType.TRANSFER]),
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )
    )
    return int(total or 0)


def estimate(
    db: DbSession,
    user_id: uuid.UUID,
    *,
    timezone_name: str | None = None,
    months: int = MINIMUM_MONTHS,
    reserves: int = 0,
    now: datetime | None = None,
) -> Capacity:
    """Average monthly capacity over the last `months` whole months."""
    now = now or datetime.now(timezone.utc)
    zone = get_zone(timezone_name)
    windows = _months_back(now, zone, months)

    income = expenses = obligations = 0
    observed = 0

    for period in windows:
        # Income accounts carry credit balances; negate to read naturally.
        # Opening balances credit equity, not income, so they are already
        # out (AC01). Transfers touch no income account either (AC02).
        month_income = -_sum_entries(db, user_id, AccountKind.INCOME, period.start, period.end)
        month_expenses = _sum_cash_expenses(db, user_id, period.start, period.end)
        month_obligations = _sum_card_payments(db, user_id, period.start, period.end)

        income += month_income
        expenses += month_expenses
        obligations += month_obligations

        if month_income or month_expenses or month_obligations:
            observed += 1

    divisor = max(1, len(windows))

    return compute_capacity(
        CapacityInputs(
            reliable_income=income // divisor,
            cash_expenses=expenses // divisor,
            obligations=obligations // divisor,
            reserves=reserves,
            # Deliberately zero. An allocation earmarks money the user
            # already holds; it is not a recurring outgoing, so counting
            # it against a monthly capacity would subtract savings from
            # the ability to save. Scheduled deposits, once goals carry
            # them, belong here instead.
            committed_deposits=0,
        ),
        months_observed=observed,
    )
