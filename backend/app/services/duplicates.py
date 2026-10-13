"""Refusing to record the same money twice (FR02, AC04).

A draft is built from what the model proposed, and the model proposes
from a conversation it re-reads every turn. That is the hole: asked to
record one new purchase, it came back with a batch holding three it had
already posted, because the thread still mentioned them. Swiping that
through charged the first purchases again, and the idempotency key
cannot catch it — a fresh draft is a fresh operation, which is exactly
what is wanted everywhere else.

Telling the model not to is not enough. It was told, in the prompt and
in the corrective nudge, and it did it anyway; `domain/categories.py`
records the same lesson about category names. So the rule lives here,
where it is a rule rather than a hope.

**What counts as the same money**: the same transaction type, on the
same day in the owner's timezone, with exactly the same legs — the same
accounts moving the same signed amounts. Not "similar": identical. Two
coffees of the same price from the same wallet on the same day really
are indistinguishable in a ledger, so the owner gets a way to say they
happened (`duplicate_ok`), and manual entry never passes through here
at all.

**Why the day and not a window of minutes**: a transaction the user
dated themselves is stored at 12:00 UTC, so its time of day carries no
information and any minute-based window would be measuring an artefact.
The day is the grain the ledger actually has.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..domain.ledger import Leg
from ..models import Transaction, TransactionStatus, TransactionType


def _signature(legs: list[Leg]) -> list[tuple[str, int]]:
    """The legs in a comparable order.

    Sorted, because leg order is a construction detail: the same
    purchase built twice may list the wallet first one time and the
    category first the next, and that is not a difference.
    """
    return sorted((str(leg.account_id), leg.amount) for leg in legs)


def _entry_signature(transaction: Transaction) -> list[tuple[str, int]]:
    return sorted((str(entry.account_id), entry.amount) for entry in transaction.entries)


def posted_twin(
    db: DbSession,
    user_id: uuid.UUID,
    *,
    tx_type: TransactionType,
    legs: list[Leg],
    occurred_at: datetime,
    zone: ZoneInfo,
) -> Transaction | None:
    """An already-posted transaction identical to the one proposed.

    Only POSTED rows count. A reversed transaction is one the owner
    undid, and recording it again is a correction, not a duplicate.
    """
    if not legs:
        return None

    day = occurred_at.astimezone(zone).date()
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = start + timedelta(days=1)

    candidates = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.type == tx_type,
            Transaction.status == TransactionStatus.POSTED,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )
    ).all()

    wanted = _signature(legs)

    for transaction in candidates:
        if _entry_signature(transaction) == wanted:
            return transaction

    return None
