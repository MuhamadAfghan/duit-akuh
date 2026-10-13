"""Not recording the same money twice (FR02, AC04).

The model proposes from a conversation it re-reads every turn, so a
draft can hold purchases it already posted — asked to record one new
expense it came back with a batch of four, three of them already in the
ledger. The idempotency key does not help: a fresh draft is a fresh
operation, which everywhere else is the point.

Two gates, and they are not redundant. The draft gate keeps the card
honest, so the user never sees money they already spent offered back to
them. The confirm gate is what makes it a rule: a card raised before
the check existed, or two cards left open in two tabs, still cannot
post the same transaction twice.

What counts as the same: identical legs, same type, same day in the
owner's timezone. Two genuinely identical purchases in one day are
indistinguishable in a ledger, so the owner can say so — and manual
entry never comes through here.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.ai.fake import text, tool

from .conftest import balances, make_account, requires_db, send

pytestmark = [requires_db, pytest.mark.integration]


def entry(amount: int, category: str = "Makan", **extra) -> dict:
    return {
        "type": "expense",
        "amount": amount,
        "from_account": "cash",
        "category": category,
        **extra,
    }


def propose(chat, *entries, message: str = "catat ya") -> dict:
    """One propose_transactions call. Returns the whole turn."""
    chat.adapter.queue(tool("propose_transactions", {"transactions": list(entries)}))
    chat.adapter.queue(text("Ini draftnya."))

    return send(chat, message)


def tool_result(chat) -> str:
    messages = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"]
    assert messages, "no tool result was fed back"

    return messages[-1]["content"]


def post_one(chat, amount: int, category: str = "Makan") -> None:
    """Record and confirm one expense, as a user would."""
    draft = propose(chat, entry(amount, category))["drafts"][0]
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200


# ----------------------------------------------------------------------
# The draft gate
# ----------------------------------------------------------------------


def test_an_already_posted_entry_is_left_out_of_a_new_batch(chat):
    """The reported bug, in its smallest form."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    post_one(chat, 5_000, "Belanja")

    turn = propose(chat, entry(5_000, "Belanja"), entry(17_000, "Makan"))
    draft = turn["drafts"][0]
    amounts = [row["amount"] for row in draft["payload"]["items"]]

    assert amounts == [17_000], "only the new purchase belongs on the card"
    assert "sudah_tercatat" in tool_result(chat), "and the model has to be told why"


def test_a_wholly_repeated_message_raises_no_draft_at_all(chat):
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    post_one(chat, 5_000, "Belanja")

    chat.adapter.queue(tool("propose_transactions", {"transactions": [entry(5_000, "Belanja")]}))
    chat.adapter.queue(text("Sudah tercatat tadi."))
    turn = send(chat, "fotocopy 5rb pake cash")

    assert turn["drafts"] == []
    assert "Sudah tercatat sebelumnya" in tool_result(chat)


def test_confirming_the_trimmed_batch_moves_money_once(chat):
    """The point of all of it: the balance.

    Before the guard this second confirmation took 22.000 out of a
    wallet that owed only 17.000 of it.
    """
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    post_one(chat, 5_000, "Belanja")
    assert balances(chat)["Cash"] == 855_000

    draft = propose(chat, entry(5_000, "Belanja"), entry(17_000, "Makan"))["drafts"][0]
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    assert balances(chat)["Cash"] == 838_000


# ----------------------------------------------------------------------
# What must still get through
# ----------------------------------------------------------------------


def test_a_different_amount_is_not_a_duplicate(chat):
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    post_one(chat, 5_000, "Belanja")

    draft = propose(chat, entry(6_000, "Belanja"))["drafts"][0]

    assert draft["payload"]["amount"] == 6_000


def test_a_different_category_is_not_a_duplicate(chat):
    """Same wallet, same money, different thing bought."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    post_one(chat, 5_000, "Belanja")

    draft = propose(chat, entry(5_000, "Makan"))["drafts"][0]

    assert draft["payload"]["amount"] == 5_000


def test_the_same_purchase_yesterday_does_not_block_today(chat):
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    yesterday = propose(chat, entry(5_000, "Belanja", occurred_on="2026-10-12"))["drafts"][0]
    assert chat.post(f"/chat/drafts/{yesterday['id']}/confirm").status_code == 200

    draft = propose(chat, entry(5_000, "Belanja", occurred_on="2026-10-13"))["drafts"][0]

    assert draft["payload"]["amount"] == 5_000


def test_the_owner_can_say_it_really_happened_twice(chat):
    """Two identical coffees in a day are indistinguishable in a ledger."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    post_one(chat, 20_000, "Makan")

    draft = propose(chat, entry(20_000, "Makan", duplicate_ok=True))["drafts"][0]
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    assert balances(chat)["Cash"] == 820_000


def test_a_reversed_transaction_can_be_recorded_again(chat):
    """Undoing it means it is not there; re-entering it is a correction."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    draft = propose(chat, entry(5_000, "Belanja"))["drafts"][0]
    confirmed = chat.post(f"/chat/drafts/{draft['id']}/confirm")
    assert confirmed.status_code == 200

    reversal = chat.post(
        f"/transactions/{confirmed.json()['transaction_id']}/reverse",
        headers={"Idempotency-Key": f"rev-{uuid.uuid4().hex}"},
    )
    assert reversal.status_code == 201, reversal.text

    again = propose(chat, entry(5_000, "Belanja"))["drafts"][0]

    assert again["payload"]["amount"] == 5_000


# ----------------------------------------------------------------------
# The confirm gate: two cards, one purchase
# ----------------------------------------------------------------------


def test_a_card_left_open_cannot_post_what_another_card_already_did(chat):
    """Both drafts were raised before either was posted, so neither was
    a duplicate when it was built. The second swipe is."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")

    first = propose(chat, entry(5_000, "Belanja"))["drafts"][0]
    second = propose(chat, entry(5_000, "Belanja"))["drafts"][0]
    assert first["id"] != second["id"]

    assert chat.post(f"/chat/drafts/{first['id']}/confirm").status_code == 200

    refused = chat.post(f"/chat/drafts/{second['id']}/confirm")

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "already_posted"
    assert balances(chat)["Cash"] == 855_000


def test_the_same_gate_covers_a_batch(chat):
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")

    first = propose(chat, entry(5_000, "Belanja"), entry(17_000, "Makan"))["drafts"][0]
    second = propose(chat, entry(5_000, "Belanja"), entry(17_000, "Makan"))["drafts"][0]

    assert chat.post(f"/chat/drafts/{first['id']}/confirm").status_code == 200

    refused = chat.post(f"/chat/drafts/{second['id']}/confirm")

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "already_posted"
    assert balances(chat)["Cash"] == 838_000
