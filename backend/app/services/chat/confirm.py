"""Confirming a draft (PRD FR05).

Posting happens from the stored :class:`Draft` row, never from the
model's output a second time. That is what makes "what you saw is what
was written" true: the payload was validated when the card was built,
and confirming replays exactly it.

The draft's ``operation_id`` is the idempotency key, so a double tap, a
retried request, or a tap on a card left open in another tab all land on
the same transaction (AC04, AC13).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...api.schemas import Draft as DraftSchema
from ...domain.errors import AllocationExceedsBalance
from ...domain.ledger import Leg, build_reversal
from ...domain.periods import get_zone
from ...models import (
    AccountType,
    Draft,
    DraftStatus,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
)
from ..accounts import open_account_with_balance
from ..budgets import set_budget
from ..drafts import TRANSACTION_TYPES, build_legs, occurred_at_of
from ..goals import allocate, create_goal
from ..posting import post_transaction


class DraftNotPending(Exception):
    code = "draft_not_pending"


class BatchIncomplete(DraftNotPending):
    """A batch with an entry whose wallet nobody has chosen yet.

    The card leaves the slot blank and offers the wallets; this is the
    gate behind it. A UI check alone would mean the rule lives only in
    the client, and AC04's "never guess" has to hold against a request
    the client did not make.
    """

    code = "batch_incomplete"


def confirm_draft(db: DbSession, *, user_id: uuid.UUID, draft: Draft) -> dict:
    """Apply a pending draft. Returns a small summary for the chat card."""
    if draft.status is not DraftStatus.PENDING:
        raise DraftNotPending(f"Draft sudah {draft.status.value}")

    if draft.kind == "account":
        return _confirm_account(db, user_id, draft)

    if draft.kind == "reversal":
        return _confirm_reversal(db, user_id, draft)

    if draft.kind == "goal":
        return _confirm_goal(db, user_id, draft)

    if draft.kind == "allocation":
        return _confirm_allocation(db, user_id, draft)

    if draft.kind == "budget":
        return _confirm_budget(db, user_id, draft)

    if draft.kind == "batch":
        return _confirm_batch(db, user_id, draft)

    return _confirm_transaction(db, user_id, draft)


def _confirm_batch(db: DbSession, user_id: uuid.UUID, draft: Draft) -> dict:
    """Post several entries as one act.

    One swipe, one group, and all of it or none of it: these came from
    one sentence, so a half-written batch would leave the person with
    a ledger that matches neither what they said nor what they saw. The
    session is not committed here, so a failure part-way rolls the
    earlier entries back with it.

    Each entry still gets its *own* idempotency key, derived from the
    draft's operation id and the entry's position. One shared key would
    make the second entry look like a replay of the first and silently
    drop it; separate ones keep a retried confirmation landing on the
    same rows (AC04, AC13).

    The stated total is not posted. It never was a transaction - only a
    claim about these entries, already checked by `reconcile` when the
    card was built.
    """
    items = draft.payload.get("items") or []

    if not items:
        raise DraftNotPending("Draft tidak punya catatan")

    if any(item.get("unresolved") for item in items):
        raise BatchIncomplete("Masih ada catatan yang kantongnya belum dipilih")

    zone = get_zone(getattr(db.get(User, user_id), "timezone", None))
    group_id = uuid.uuid4()

    posted = []
    replayed = True

    for index, item in enumerate(items):
        payload = {key: value for key, value in item.items() if key != "unresolved"}
        parsed = TypeAdapter(DraftSchema).validate_python(payload)

        result = post_transaction(
            db,
            user_id=user_id,
            tx_type=TRANSACTION_TYPES[parsed.type],
            occurred_at=occurred_at_of(parsed, zone),
            legs=build_legs(db, user_id, parsed),
            idempotency_key=f"{draft.operation_id}:{index}",
            merchant=parsed.merchant,
            note=parsed.note,
            source="chat",
            allow_negative=parsed.allow_negative,
            operation_id=draft.operation_id,
            group_id=group_id,
        )

        posted.append(str(result.transaction.id))
        replayed = replayed and result.replayed

    draft.status = DraftStatus.CONFIRMED
    # One column, several transactions: the first stands for the group
    # so a card can still link somewhere, and `group_id` is what ties
    # the rest of them together.
    draft.transaction_id = uuid.UUID(posted[0])
    db.flush()

    return {
        "draft_id": str(draft.id),
        "group_id": str(group_id),
        "transaction_ids": posted,
        "replayed": replayed,
    }


def _confirm_transaction(db: DbSession, user_id: uuid.UUID, draft: Draft) -> dict:
    parsed = TypeAdapter(DraftSchema).validate_python(draft.payload)
    legs = build_legs(db, user_id, parsed)

    # A stored payload can hold an offset-less date if whatever drafted
    # it wrote one; reading it as the owner's wall clock beats letting
    # the column type refuse it at confirmation time.
    zone = get_zone(getattr(db.get(User, user_id), "timezone", None))

    result = post_transaction(
        db,
        user_id=user_id,
        tx_type=TRANSACTION_TYPES[parsed.type],
        occurred_at=occurred_at_of(parsed, zone),
        legs=legs,
        idempotency_key=draft.operation_id,
        merchant=parsed.merchant,
        note=parsed.note,
        source="chat",
        allow_negative=parsed.allow_negative,
        operation_id=draft.operation_id,
    )

    draft.status = DraftStatus.CONFIRMED
    draft.transaction_id = result.transaction.id
    db.flush()

    return {
        "draft_id": str(draft.id),
        "transaction_id": str(result.transaction.id),
        "replayed": result.replayed,
    }


def _confirm_account(db: DbSession, user_id: uuid.UUID, draft: Draft) -> dict:
    payload = draft.payload

    account, _ = open_account_with_balance(
        db,
        user_id=user_id,
        name=payload["name"],
        account_type=AccountType(payload["type"]),
        opening_balance=payload.get("opening_balance") or 0,
        credit_limit=payload.get("credit_limit"),
        occurred_at=datetime.now(timezone.utc),
        # Reuse the draft's operation id so confirming twice cannot
        # create the opening balance twice.
        idempotency_key=draft.operation_id,
    )

    draft.status = DraftStatus.CONFIRMED
    db.flush()

    return {"draft_id": str(draft.id), "account_id": str(account.id), "replayed": False}


def _confirm_goal(db: DbSession, user_id: uuid.UUID, draft: Draft) -> dict:
    payload = draft.payload
    target_date = payload.get("target_date")

    goal = create_goal(
        db,
        user_id=user_id,
        name=payload["name"],
        target_amount=payload["target_amount"],
        target_date=datetime.fromisoformat(target_date) if target_date else None,
        priority=payload.get("priority", 0),
    )

    draft.status = DraftStatus.CONFIRMED
    db.flush()

    return {"draft_id": str(draft.id), "goal_id": str(goal.id), "replayed": False}


def _confirm_allocation(db: DbSession, user_id: uuid.UUID, draft: Draft) -> dict:
    payload = draft.payload

    try:
        allocation = allocate(
            db,
            user_id=user_id,
            goal_id=uuid.UUID(payload["goal_id"]),
            account_id=uuid.UUID(payload["account_id"]),
            amount=payload["amount"],
        )
    except AllocationExceedsBalance as exc:
        # The balance moved between drafting and confirming, so the card
        # no longer describes what would happen (FR15).
        draft.status = DraftStatus.STALE
        db.flush()
        raise DraftNotPending(str(exc)) from exc

    draft.status = DraftStatus.CONFIRMED
    db.flush()

    return {
        "draft_id": str(draft.id),
        "allocation_id": str(allocation.id),
        "replayed": False,
    }


def _confirm_budget(db: DbSession, user_id: uuid.UUID, draft: Draft) -> dict:
    budget = set_budget(
        db,
        user_id=user_id,
        category=draft.payload["category"],
        amount=draft.payload["amount"],
    )

    draft.status = DraftStatus.CONFIRMED
    db.flush()

    return {"draft_id": str(draft.id), "budget_id": str(budget.id), "replayed": False}


def _confirm_reversal(db: DbSession, user_id: uuid.UUID, draft: Draft) -> dict:
    original = db.scalar(
        select(Transaction).where(
            Transaction.id == uuid.UUID(draft.payload["transaction_id"]),
            Transaction.user_id == user_id,
        )
    )

    if original is None:
        raise DraftNotPending("Transaksi aslinya tidak ditemukan")

    if original.status is TransactionStatus.REVERSED:
        draft.status = DraftStatus.STALE
        db.flush()
        raise DraftNotPending("Transaksi ini sudah dibalik sebelumnya")

    result = post_transaction(
        db,
        user_id=user_id,
        tx_type=TransactionType.REVERSAL,
        occurred_at=original.occurred_at,
        legs=build_reversal([Leg(e.account_id, e.amount) for e in original.entries]),
        idempotency_key=draft.operation_id,
        description=f"Pembatalan {original.type.value}",
        source="chat",
        reverses_id=original.id,
        # A reversal restores a previous state; refusing it for going
        # negative would strand the user in the wrong one.
        allow_negative=True,
        operation_id=draft.operation_id,
    )

    if not result.replayed:
        original.status = TransactionStatus.REVERSED
        original.version += 1

    draft.status = DraftStatus.CONFIRMED
    draft.transaction_id = result.transaction.id
    db.flush()

    return {
        "draft_id": str(draft.id),
        "transaction_id": str(result.transaction.id),
        "replayed": result.replayed,
    }


def cancel_draft(db: DbSession, draft: Draft) -> None:
    draft.status = DraftStatus.CANCELLED
    db.flush()
