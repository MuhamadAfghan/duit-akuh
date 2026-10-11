"""Account and summary endpoints.

Every handler is scoped to ``CurrentUser``. There is no endpoint that
takes a user id as a parameter, so one user's identifier can never be
used to reach another's data (AC08).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..domain.balances import (
    AccountSnapshot,
    category_total,
    free_to_spend,
    liquid_balance,
    net_worth,
    total_debt,
)
from ..domain.periods import as_utc, get_zone
from ..models import LIQUID_TYPES, Account, AccountKind, Allocation
from ..services.accounts import open_account_with_balance
from .deps import CurrentUser, DbSessionDep
from .schemas import AccountCreateIn, AccountOut, AccountUpdateIn, SummaryOut

router = APIRouter(tags=["accounts"])


def _to_out(snapshot: AccountSnapshot, account: Account) -> AccountOut:
    return AccountOut(
        id=account.id,
        name=account.name,
        alias=account.alias,
        type=account.type,
        balance=snapshot.balance,
        debt=snapshot.debt,
        credit_limit=account.credit_limit,
        is_archived=account.is_archived,
    )


def _snapshots(db, user_id: uuid.UUID) -> list[AccountSnapshot]:
    from ..services.posting import account_snapshots

    return account_snapshots(db, user_id)


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(user: CurrentUser, db: DbSessionDep) -> list[AccountOut]:
    """The user's wallets, with balances.

    System accounts (categories, the opening-balance equity account) are
    left out: they are bookkeeping counterparts, not things the user
    holds money in.
    """
    snapshots = {s.id: s for s in _snapshots(db, user.id)}

    accounts = db.scalars(
        select(Account)
        .where(Account.user_id == user.id, Account.is_system.is_(False))
        .order_by(Account.is_archived, Account.name)
    ).all()

    return [_to_out(snapshots[a.id], a) for a in accounts]


@router.post("/accounts", status_code=status.HTTP_201_CREATED, response_model=AccountOut)
def create_account(body: AccountCreateIn, user: CurrentUser, db: DbSessionDep) -> AccountOut:
    account, _ = open_account_with_balance(
        db,
        user_id=user.id,
        name=body.name,
        account_type=body.type,
        alias=body.alias,
        opening_balance=body.opening_balance,
        credit_limit=body.credit_limit,
        occurred_at=(
            as_utc(body.occurred_at, get_zone(user.timezone))
            if body.occurred_at is not None
            else None
        ),
    )

    snapshots = {s.id: s for s in _snapshots(db, user.id)}

    return _to_out(snapshots[account.id], account)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: uuid.UUID, body: AccountUpdateIn, user: CurrentUser, db: DbSessionDep
) -> AccountOut:
    """Rename, re-alias, set a limit, or archive.

    There is no delete: an account with history is archived, never
    removed (FR01).
    """
    account = db.scalar(
        select(Account).where(
            Account.id == account_id, Account.user_id == user.id, Account.is_system.is_(False)
        )
    )

    if account is None:
        # 404 rather than 403 for an account belonging to someone else:
        # distinguishing them would confirm that the id exists.
        raise HTTPException(status_code=404, detail={"code": "account_not_found"})

    if body.name is not None:
        account.name = body.name.strip()

    if body.alias is not None:
        account.alias = body.alias.strip().lower() or None

    if body.credit_limit is not None:
        account.credit_limit = body.credit_limit

    if body.is_archived is not None:
        account.is_archived = body.is_archived

    account.version += 1
    db.flush()

    snapshots = {s.id: s for s in _snapshots(db, user.id)}

    return _to_out(snapshots[account.id], account)


@router.get("/summary", response_model=SummaryOut)
def summary(user: CurrentUser, db: DbSessionDep) -> SummaryOut:
    """The FR09 indicators, each counted once.

    Allocations are only subtracted when they sit on a liquid account —
    otherwise money that was never in ``liquid`` would be deducted from
    it.
    """
    snapshots = _snapshots(db, user.id)
    liquid_ids = {s.id for s in snapshots if s.type in LIQUID_TYPES and not s.is_archived}

    allocations = db.scalars(select(Allocation).where(Allocation.user_id == user.id)).all()
    allocated_on_liquid = sum(a.amount for a in allocations if a.account_id in liquid_ids)

    fts = free_to_spend(snapshots, allocated_on_liquid=allocated_on_liquid)

    return SummaryOut(
        liquid=liquid_balance(snapshots),
        net_worth=net_worth(snapshots),
        total_debt=total_debt(snapshots),
        allocated=allocated_on_liquid,
        free_to_spend=fts.amount,
        is_shortfall=fts.is_shortfall,
        expense_total=category_total(snapshots, kind=AccountKind.EXPENSE),
        income_total=category_total(snapshots, kind=AccountKind.INCOME),
    )
