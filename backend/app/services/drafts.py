"""Turning an API draft into balanced ledger legs.

The bridge between the wire format and :mod:`app.domain.ledger`. It
resolves category names to their system accounts — creating them on first
use — and then calls the pure builder for that event type.

Preview and posting both go through here, so what the confirmation card
shows and what is eventually written cannot drift apart.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as DbSession

from ..domain.ledger import (
    Leg,
    build_card_payment,
    build_expense,
    build_income,
    build_refund,
    build_transfer,
)
from ..domain.periods import as_utc, get_zone
from ..models import TransactionType
from .accounts import expense_category, income_category

#: Maps a draft's ``type`` to the transaction type recorded for reporting.
TRANSACTION_TYPES = {
    "expense": TransactionType.EXPENSE,
    "income": TransactionType.INCOME,
    "transfer": TransactionType.TRANSFER,
    "card_payment": TransactionType.CARD_PAYMENT,
    "refund": TransactionType.REFUND,
}


def build_legs(db: DbSession, user_id: uuid.UUID, draft) -> list[Leg]:
    """Produce the balanced legs for a draft.

    Account ids on the draft are **not** validated here; ownership is
    checked in :func:`app.services.posting.post_transaction`, which is
    the single place that touches the database on the way in.
    """
    kind = draft.type

    if kind == "expense":
        category = expense_category(db, user_id, draft.category)
        return build_expense(
            from_account_id=draft.from_account_id,
            expense_account_id=category.id,
            amount=draft.amount,
        )

    if kind == "income":
        category = income_category(db, user_id, draft.category)
        return build_income(
            to_account_id=draft.to_account_id,
            income_account_id=category.id,
            amount=draft.amount,
        )

    if kind == "transfer":
        fee_account_id = None

        if draft.fee:
            fee_account_id = expense_category(db, user_id, draft.fee_category).id

        return build_transfer(
            from_account_id=draft.from_account_id,
            to_account_id=draft.to_account_id,
            amount=draft.amount,
            fee=draft.fee,
            fee_expense_account_id=fee_account_id,
        )

    if kind == "card_payment":
        return build_card_payment(
            from_account_id=draft.from_account_id,
            card_account_id=draft.card_account_id,
            amount=draft.amount,
        )

    if kind == "refund":
        category = expense_category(db, user_id, draft.category)
        return build_refund(
            to_account_id=draft.to_account_id,
            expense_account_id=category.id,
            amount=draft.amount,
        )

    raise ValueError(f"Jenis draft tidak dikenal: {kind!r}")


def occurred_at_of(draft, zone: ZoneInfo | None = None) -> datetime:
    """When the event happened, defaulting to now.

    The PRD distinguishes this from ``created_at``: a user recording
    yesterday's lunch today needs the transaction dated yesterday.

    ``zone`` reads a client's offset-less datetime as that person's own
    wall clock. Without it a value like ``"2026-10-10T14:30:00"`` would
    reach the column type naive and be refused there, which surfaces as
    a 500 rather than a stored row.
    """
    moment = draft.occurred_at

    if moment is None:
        return datetime.now(timezone.utc)

    return as_utc(moment, zone or get_zone(None))


def describe(draft) -> str | None:
    return getattr(draft, "note", None)
