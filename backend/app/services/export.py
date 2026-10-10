"""CSV export of transactions (PRD section 9, AC10).

One row per **entry**, not per transaction. A transfer has two sides and
a transfer with a fee has three; collapsing them into one row would
force a choice about which account and which amount to show, and lose
the rest. Entry rows reconstruct the ledger exactly, and the
transaction id ties them back together.

Amounts stay integer rupiah with no thousands separator, so a
spreadsheet reads them as numbers rather than text.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..domain.periods import Period
from ..models import Account, Entry, Transaction

COLUMNS = [
    "transaction_id",
    "occurred_at",
    "type",
    "status",
    "account",
    "account_type",
    "amount",
    "category",
    "merchant",
    "note",
    "description",
    "source",
]


def _sanitise(value: str | None) -> str:
    """Neutralise spreadsheet formula injection.

    A merchant or note the user typed starting with =, +, - or @ is
    executed as a formula by Excel and Sheets on open. Prefixing an
    apostrophe keeps the text visible and inert. The data here is the
    user's own, but it also arrives from receipt OCR and chat, so it is
    not all self-authored.
    """
    if not value:
        return ""

    text = str(value)

    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def export_transactions(db: DbSession, user_id: uuid.UUID, period: Period) -> Iterator[str]:
    """Yield CSV text, one chunk at a time.

    Streamed rather than built in memory: an export is unbounded by
    nature, and the PRD targets 10,000 transactions per user.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    def flush() -> str:
        value = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return value

    writer.writerow(COLUMNS)
    yield flush()

    rows = db.execute(
        select(Transaction, Entry, Account)
        .join(Entry, Entry.transaction_id == Transaction.id)
        .join(Account, Account.id == Entry.account_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_at >= period.start,
            Transaction.occurred_at < period.end,
        )
        .order_by(Transaction.occurred_at, Transaction.id, Account.name)
        .execution_options(yield_per=500)
    )

    for transaction, entry, account in rows:
        writer.writerow(
            [
                str(transaction.id),
                transaction.occurred_at.isoformat(),
                transaction.type.value,
                transaction.status.value,
                _sanitise(account.name),
                account.type.value,
                entry.amount,
                _sanitise(account.name if account.kind.value == "expense" else ""),
                _sanitise(transaction.merchant),
                _sanitise(transaction.note),
                _sanitise(transaction.description),
                transaction.source,
            ]
        )
        yield flush()
