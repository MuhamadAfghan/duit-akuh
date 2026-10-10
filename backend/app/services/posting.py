"""Writing transactions to the ledger.

This is the only module that creates entries. Everything it does happens
inside one database transaction, so a multi-leg posting either lands
completely or not at all (FR03, AC13).

Three guarantees it is responsible for:

1. **Idempotency** — the same ``idempotency_key`` never produces a second
   transaction. A duplicate confirmation gets the original back (AC04).
2. **Ownership** — every account touched is re-checked against the calling
   user before anything is written (AC08).
3. **Balance** — legs must sum to zero, re-asserted here even though the
   builders already did it, because callers may assemble legs by hand.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.balances import AccountSnapshot
from ..domain.errors import AccountArchived, CrossUserAccess, InsufficientBalance
from ..domain.ledger import Leg, assert_balanced
from ..models import (
    Account,
    AccountKind,
    AuditEvent,
    Entry,
    Transaction,
    TransactionStatus,
    TransactionType,
    new_uuid,
)


@dataclass(frozen=True, slots=True)
class PostResult:
    transaction: Transaction
    #: True when an existing transaction was returned instead of a new one,
    #: i.e. the idempotency key had already been used.
    replayed: bool


def _load_owned_accounts(
    session: Session, user_id: uuid.UUID, account_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Account]:
    """Fetch accounts, failing loudly if any is missing or another user's.

    Filtering by ``user_id`` and then comparing counts means a foreign id
    cannot simply vanish from the result and leave an unbalanced posting;
    it raises instead.
    """
    rows = session.scalars(
        select(Account).where(Account.user_id == user_id, Account.id.in_(account_ids))
    ).all()

    found = {account.id: account for account in rows}
    missing = account_ids - found.keys()

    if missing:
        raise CrossUserAccess(
            f"Akun tidak ditemukan atau bukan milik pengguna ini: {sorted(map(str, missing))}"
        )

    return found


def account_balance(session: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> int:
    """Current balance of one account, in integer rupiah.

    Always scoped by ``user_id`` so a guessed account id returns nothing
    rather than another user's figure.
    """
    total = session.scalar(
        select(func.coalesce(func.sum(Entry.amount), 0)).where(
            Entry.user_id == user_id, Entry.account_id == account_id
        )
    )
    return int(total or 0)


def account_snapshots(session: Session, user_id: uuid.UUID) -> list[AccountSnapshot]:
    """Every account of a user with its computed balance.

    One grouped query rather than a balance query per account, so the
    dashboard stays within its FR09 latency budget as transactions grow.
    """
    totals = dict(
        session.execute(
            select(Entry.account_id, func.coalesce(func.sum(Entry.amount), 0))
            .where(Entry.user_id == user_id)
            .group_by(Entry.account_id)
        ).all()
    )

    accounts = session.scalars(select(Account).where(Account.user_id == user_id)).all()

    return [
        AccountSnapshot(
            id=account.id,
            name=account.name,
            type=account.type,
            kind=account.kind,
            balance=int(totals.get(account.id, 0)),
            is_archived=account.is_archived,
            credit_limit=account.credit_limit,
        )
        for account in accounts
    ]


def post_transaction(
    session: Session,
    *,
    user_id: uuid.UUID,
    tx_type: TransactionType,
    occurred_at: datetime,
    legs: list[Leg],
    idempotency_key: str,
    description: str | None = None,
    merchant: str | None = None,
    note: str | None = None,
    source: str = "manual",
    reverses_id: uuid.UUID | None = None,
    allow_negative: bool = False,
    operation_id: str | None = None,
) -> PostResult:
    """Write one balanced transaction, idempotently.

    ``allow_negative`` must be set explicitly to let an asset balance go
    below zero. The PRD permits it only after a warning and an explicit
    confirmation, so the default refuses.
    """
    assert_balanced(legs)

    # Replay check first: the common duplicate (a retried confirmation)
    # should not even attempt a write.
    existing = session.scalar(
        select(Transaction).where(
            Transaction.user_id == user_id, Transaction.idempotency_key == idempotency_key
        )
    )

    if existing is not None:
        return PostResult(transaction=existing, replayed=True)

    account_ids = {leg.account_id for leg in legs}
    accounts = _load_owned_accounts(session, user_id, account_ids)

    for account in accounts.values():
        if account.is_archived:
            raise AccountArchived(f"Akun '{account.name}' sudah diarsipkan")

    if not allow_negative:
        _reject_overdraft(session, user_id, legs, accounts)

    transaction = Transaction(
        # Assigned here rather than left to the column default, which only
        # runs at INSERT: the audit event below needs the id, and a
        # column default would still be None at that point.
        id=new_uuid(),
        user_id=user_id,
        type=tx_type,
        status=TransactionStatus.POSTED,
        occurred_at=occurred_at,
        description=description,
        merchant=merchant,
        note=note,
        source=source,
        idempotency_key=idempotency_key,
        reverses_id=reverses_id,
    )
    transaction.entries = [
        Entry(user_id=user_id, account_id=leg.account_id, amount=leg.amount) for leg in legs
    ]

    session.add(transaction)

    try:
        session.flush()
    except IntegrityError:
        # Lost a race against a concurrent request with the same key. The
        # unique constraint is the real guarantee; the earlier check is
        # only an optimisation.
        session.rollback()
        winner = session.scalar(
            select(Transaction).where(
                Transaction.user_id == user_id, Transaction.idempotency_key == idempotency_key
            )
        )
        if winner is None:
            raise
        return PostResult(transaction=winner, replayed=True)

    # Audited only after the transaction is known to have landed. Writing
    # the event first would leave an audit trail claiming a posting that
    # the unique constraint then rejected.
    session.add(
        AuditEvent(
            user_id=user_id,
            action="transaction.posted",
            object_type="transaction",
            object_id=transaction.id,
            operation_id=operation_id,
            after={
                "type": tx_type.value,
                "entries": [
                    {"account_id": str(leg.account_id), "amount": leg.amount} for leg in legs
                ],
            },
        )
    )
    session.flush()

    return PostResult(transaction=transaction, replayed=False)


def _reject_overdraft(
    session: Session,
    user_id: uuid.UUID,
    legs: list[Leg],
    accounts: dict[uuid.UUID, Account],
) -> None:
    """Refuse to drive an asset account negative without confirmation.

    Liabilities are skipped: a credit card going "negative" in ledger terms
    simply means debt, which is its normal state.
    """
    deltas: dict[uuid.UUID, int] = {}

    for leg in legs:
        deltas[leg.account_id] = deltas.get(leg.account_id, 0) + leg.amount

    for account_id, delta in deltas.items():
        account = accounts[account_id]

        if account.kind is not AccountKind.ASSET or delta >= 0:
            continue

        current = account_balance(session, user_id, account_id)

        if current + delta < 0:
            raise InsufficientBalance(
                f"Saldo '{account.name}' akan menjadi {current + delta}. "
                "Konfirmasi eksplisit diperlukan untuk saldo negatif."
            )
