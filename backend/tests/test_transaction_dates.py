"""Which day a transaction belongs to, as told to the model.

Entries are stored in UTC; the day a person means is the day it was
where they are. `domain/periods.py` already states the rule for months
— "a purchase at 06:00 on 1 October local time is 23:00 on 30 September
UTC, so a naive UTC month boundary files it in the wrong month" — and
`find_transactions` was the one place that broke it for days, by taking
`.date()` straight off the stored value.

For Asia/Jakarta that is a seven-hour shift, so everything bought
between midnight and 07:00 was handed to the model under the previous
day's date. The summary and the data screen called it today; the chat
called it yesterday, and the model had no way to be right.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.ai.fake import text, tool

from .conftest import make_account, requires_db, send

pytestmark = [requires_db, pytest.mark.integration]

#: 2026-10-13 01:30 in Jakarta. Stored UTC lands on the 12th, which is
#: exactly the window the bug lived in.
AFTER_MIDNIGHT_WIB = "2026-10-12T18:30:00+00:00"
#: 2026-10-12 19:00 in Jakarta — the same UTC day as the local one, so
#: this one was never wrong and must not become wrong.
EVENING_WIB = "2026-10-12T12:00:00+00:00"


def post(chat, account_id: str, *, amount: int, occurred_at: str, merchant: str) -> None:
    response = chat.post(
        "/transactions",
        json={
            "type": "expense",
            "amount": amount,
            "from_account_id": account_id,
            "category": "Transportasi",
            "merchant": merchant,
            "occurred_at": occurred_at,
        },
        headers={"Idempotency-Key": f"date-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 201, response.text


def dates_shown_to_model(chat) -> dict[str, str]:
    """{merchant: date} exactly as `find_transactions` reported it."""
    import json

    chat.adapter.queue(tool("find_transactions", {}))
    chat.adapter.queue(text("Ini transaksinya."))
    send(chat, "transaksi terakhir apa")

    results = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"]
    payload = json.loads(results[-1]["content"])

    # Opening balances come back too, carrying no merchant. They are
    # dated "now" and would collide on one key.
    return {row["merchant"]: row["date"] for row in payload["transactions"] if row["merchant"]}


def test_a_purchase_after_midnight_keeps_its_local_date(chat):
    """The defect: 01:30 in Jakarta was reported as the previous day."""
    account = make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")
    post(chat, account["id"], amount=3_500, occurred_at=AFTER_MIDNIGHT_WIB, merchant="TJ")

    assert dates_shown_to_model(chat)["TJ"] == "2026-10-13"


def test_an_evening_purchase_is_unchanged(chat):
    """The fix must not shift the hours that were already right."""
    account = make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")
    post(chat, account["id"], amount=25_000, occurred_at=EVENING_WIB, merchant="Bus")

    assert dates_shown_to_model(chat)["Bus"] == "2026-10-12"


def test_two_purchases_hours_apart_are_told_apart(chat):
    """The shape of the bug report: one list, two days, one of them wrong.

    Both of these sit on 2026-10-12 in UTC, so before the fix the model
    was handed the same date for both and could only guess which was
    which — which is how three of yesterday's fares were narrated as
    today's.
    """
    account = make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")
    post(chat, account["id"], amount=25_000, occurred_at=EVENING_WIB, merchant="Bus")
    post(chat, account["id"], amount=3_500, occurred_at=AFTER_MIDNIGHT_WIB, merchant="TJ")

    assert dates_shown_to_model(chat) == {"Bus": "2026-10-12", "TJ": "2026-10-13"}
