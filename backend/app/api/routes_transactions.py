"""Transaction endpoints: preview, post, list, reverse.

``/transactions/preview`` and ``/transactions`` take the same draft body
and build legs through the same code path, so the impact the user
confirms is the impact that gets written.

Posting requires an ``Idempotency-Key`` header. It is not optional: AC04
requires a confirmation sent twice to produce exactly one transaction,
and a client that forgets the header would otherwise silently lose that
guarantee.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import select

from ..domain.balances import impact_of
from ..domain.errors import InsufficientBalance
from ..models import AccountKind, Transaction, TransactionStatus, TransactionType
from ..services.drafts import TRANSACTION_TYPES, build_legs, occurred_at_of
from ..services.posting import account_snapshots, post_transaction
from .deps import CurrentUser, DbSessionDep
from .schemas import Draft, EntryOut, ImpactOut, PreviewOut, TransactionOut

router = APIRouter(prefix="/transactions", tags=["transactions"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        description="Unique per confirmed action. Replaying it returns the original transaction.",
    ),
]


def _to_out(transaction: Transaction, *, replayed: bool) -> TransactionOut:
    return TransactionOut(
        id=transaction.id,
        type=transaction.type,
        occurred_at=transaction.occurred_at,
        description=transaction.description,
        merchant=transaction.merchant,
        note=transaction.note,
        entries=[EntryOut(account_id=e.account_id, amount=e.amount) for e in transaction.entries],
        replayed=replayed,
    )


@router.post("/preview", response_model=PreviewOut)
def preview(body: Draft, user: CurrentUser, db: DbSessionDep) -> PreviewOut:
    """Compute a draft's effect without writing anything.

    This is what the chat's confirmation card renders. It is a read in
    product terms — nothing is saved and nothing needs confirming — so
    the PRD does not require a confirmation step to reach it.
    """
    legs = build_legs(db, user.id, body)
    snapshots = account_snapshots(db, user.id)
    rows = impact_of(legs, snapshots)

    by_id = {s.id: s for s in snapshots}
    would_overdraw = any(
        by_id.get(row.account_id) is not None
        and by_id[row.account_id].kind is AccountKind.ASSET
        and row.after < 0
        for row in rows
    )

    return PreviewOut(
        impact=[
            ImpactOut(
                account_id=row.account_id,
                name=row.name,
                before=row.before,
                after=row.after,
                delta=row.delta,
            )
            for row in rows
        ],
        would_overdraw=would_overdraw,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TransactionOut)
def create_transaction(
    body: Draft,
    idempotency_key: IdempotencyKey,
    user: CurrentUser,
    db: DbSessionDep,
) -> TransactionOut:
    """Post a confirmed draft.

    Replaying the same ``Idempotency-Key`` returns the original
    transaction with ``replayed: true`` rather than creating a second one.
    """
    legs = build_legs(db, user.id, body)

    result = post_transaction(
        db,
        user_id=user.id,
        tx_type=TRANSACTION_TYPES[body.type],
        occurred_at=occurred_at_of(body),
        legs=legs,
        idempotency_key=idempotency_key,
        merchant=body.merchant,
        note=body.note,
        source="api",
        allow_negative=body.allow_negative,
        operation_id=idempotency_key,
    )

    return _to_out(result.transaction, replayed=result.replayed)


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    user: CurrentUser,
    db: DbSessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TransactionOut]:
    """Most recent first, scoped to the caller."""
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.occurred_at.desc(), Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [_to_out(t, replayed=False) for t in rows]


@router.post("/{transaction_id}/reverse", status_code=status.HTTP_201_CREATED)
def reverse_transaction(
    transaction_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
    user: CurrentUser,
    db: DbSessionDep,
) -> TransactionOut:
    """Undo a transaction by posting its mirror image.

    Nothing is deleted. The original stays, a reversal is added pointing
    at it, and the original is marked reversed — so the history remains
    traceable, which is what FR02 and AC08 require of a correction.
    """
    from ..domain.ledger import Leg, build_reversal

    original = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user.id)
    )

    if original is None:
        raise HTTPException(status_code=404, detail={"code": "transaction_not_found"})

    if original.status is TransactionStatus.REVERSED:
        raise HTTPException(
            status_code=409,
            detail={"code": "already_reversed", "message": "Transaksi ini sudah dibalik"},
        )

    legs = build_reversal([Leg(e.account_id, e.amount) for e in original.entries])

    try:
        result = post_transaction(
            db,
            user_id=user.id,
            tx_type=TransactionType.REVERSAL,
            occurred_at=original.occurred_at,
            legs=legs,
            idempotency_key=idempotency_key,
            description=f"Pembatalan {original.type.value}",
            source="api",
            reverses_id=original.id,
            # A reversal restores a previous state, so refusing it for
            # going negative would strand the user in the wrong one.
            allow_negative=True,
        )
    except InsufficientBalance as exc:  # pragma: no cover - allow_negative is set
        raise HTTPException(status_code=422, detail={"code": exc.code}) from exc

    if not result.replayed:
        original.status = TransactionStatus.REVERSED
        original.version += 1
        db.flush()

    return _to_out(result.transaction, replayed=result.replayed)
