"""Keeping one category one category, and moving things between them.

Two faults, one report. The breakdown showed "transport" and "ongkos"
as separate lines for the same thing, and asking for them to be merged
produced a cancellation card — right sentence, wrong act: it offered to
hand the money back.

So there are two halves here. One spelling per category, enforced where
the account is looked up rather than hoped for from the model. And a
move that touches no wallet, because filing a purchase under the wrong
word is not a money mistake and undoing it must not move money.
"""

from __future__ import annotations

import uuid

import pytest

from app.models import AccountKind
from app.services.ai.fake import FakeAdapter, text, tool

from .conftest import balances, make_account, requires_db, send

pytestmark = [requires_db, pytest.mark.integration]


def tool_error(client) -> str:
    """What the last tool call handed back to the model."""
    messages = [m for m in client.adapter.calls[-1]["messages"] if m["role"] == "tool"]
    assert messages, "no tool result was fed back"
    return messages[-1]["content"]


def spending(client) -> dict[str, int]:
    """This month's expense breakdown, as {category: amount}."""
    response = client.get("/reports/spending")
    assert response.status_code == 200, response.text
    return {row["name"]: row["amount"] for row in response.json()["categories"]}


def expense(client, amount: int, category: str, account: str = "bca") -> dict:
    """Record and confirm one expense through the chat, as a user would."""
    client.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": amount,
                        "from_account": account,
                        "category": category,
                    }
                ]
            },
        )
    )
    client.adapter.queue(text("Ini draftnya."))
    draft = send(client, f"{category} {amount}")["drafts"][0]
    assert client.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200
    return draft


# ----------------------------------------------------------------------
# One spelling per category
# ----------------------------------------------------------------------


def test_case_does_not_split_a_category(chat):
    """"transport" and "Transport" are one thing, and must read as one.

    A fresh group is created under its canonical name, so the row is
    headed "Transportasi" even though nobody typed it. That is the
    taxonomy doing its job; what matters here is that three spellings
    produced one row.
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    expense(chat, 25_000, "transport")
    expense(chat, 33_500, "Transport")
    expense(chat, 10_000, "TRANSPORT")

    assert spending(chat) == {"Transportasi": 68_500}


def test_synonyms_land_in_one_category(chat):
    """The reason the groups exist: one thing, one row, whatever it is called."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    expense(chat, 25_000, "ongkos")
    expense(chat, 33_500, "bensin")
    expense(chat, 10_000, "parkir")

    assert spending(chat) == {"Transportasi": 68_500}


def test_a_new_category_is_stored_capitalised_without_mangling_acronyms(chat):
    """A name in no group passes through, tidied but not translated.

    This is a seed list, not a closed taxonomy, so "KPR" has to stay
    "KPR" rather than being lower-cased or argued into "Lain-lain".
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    expense(chat, 20_000, "  kucing  ")
    expense(chat, 30_000, "KPR")

    assert spending(chat) == {"Kucing": 20_000, "KPR": 30_000}


def test_the_model_is_shown_the_categories_it_already_has(chat):
    """The only thing that can stop it inventing a synonym is seeing them."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    expense(chat, 25_000, "Transport")

    chat.adapter.queue(text("Oke."))
    send(chat, "halo")

    system = chat.adapter.calls[-1]["messages"][0]["content"]
    assert "Kategori yang sudah dipakai pengguna" in system
    assert "- Transport" in system


def test_a_budget_sees_spending_written_in_another_case(chat):
    """The split was not only cosmetic: a budget missed half its spend."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    expense(chat, 40_000, "transport")
    expense(chat, 60_000, "Transport")

    assert chat.put("/budgets", json={"category": "TRANSPORT", "amount": 150_000}).status_code == 200

    rows = {row["category"]: row for row in chat.get("/budgets").json()["budgets"]}
    assert rows["Transportasi"]["spent"] == 100_000


# ----------------------------------------------------------------------
# Moving between categories
# ----------------------------------------------------------------------


def test_moving_one_transaction_leaves_every_wallet_alone(chat):
    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")

    expense(chat, 25_000, "Ongkos", account="cash")
    before = balances(chat)["Cash"]

    transaction_id = chat.get("/transactions").json()[0]["id"]

    chat.adapter.queue(
        tool(
            "propose_recategorise",
            {"transaction_id": transaction_id, "to_category": "Makan"},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "ongkos itu masukin ke makan")["drafts"][0]

    assert draft["kind"] == "recategorise"
    assert draft["payload"]["from_category"] == "Transportasi"
    assert draft["payload"]["to_category"] == "Makan"
    assert draft["payload"]["amount"] == 25_000
    assert draft["payload"]["count"] == 1

    # Nothing written yet.
    assert balances(chat)["Cash"] == before
    assert spending(chat) == {"Transportasi": 25_000}

    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    # The whole point: the money did not move.
    assert balances(chat)["Cash"] == before
    assert spending(chat) == {"Makan": 25_000}


def test_merging_a_category_moves_all_of_it_at_once(chat):
    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")

    expense(chat, 25_000, "Ongkos", account="cash")
    expense(chat, 15_000, "Ongkos", account="cash")
    expense(chat, 58_500, "Jajan", account="cash")
    before = balances(chat)["Cash"]

    chat.adapter.queue(
        tool(
            "propose_recategorise",
            {"from_category": "ongkos", "to_category": "makan"},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "ongkos merge ke makan aja")["drafts"][0]

    assert draft["payload"]["count"] == 2
    assert draft["payload"]["amount"] == 40_000

    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    assert balances(chat)["Cash"] == before
    assert spending(chat) == {"Makan": 98_500}


def test_a_move_changes_neither_the_total_nor_the_income(chat):
    """A reclassification is not income and not a second expense."""
    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")

    expense(chat, 25_000, "Ongkos", account="cash")
    report = chat.get("/reports/spending").json()
    totals = (report["expense_total"], report["income_total"])

    chat.adapter.queue(
        tool("propose_recategorise", {"from_category": "Ongkos", "to_category": "Makan"})
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "pindahin")["drafts"][0]
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    after = chat.get("/reports/spending").json()
    assert (after["expense_total"], after["income_total"]) == totals


def test_confirming_a_move_twice_moves_it_once(chat):
    """AC13 again: each posting carries its own idempotency key."""
    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")

    expense(chat, 25_000, "Ongkos", account="cash")
    expense(chat, 15_000, "Ongkos", account="cash")

    chat.adapter.queue(
        tool("propose_recategorise", {"from_category": "Ongkos", "to_category": "Makan"})
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "pindahin")["drafts"][0]

    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 404

    assert spending(chat) == {"Makan": 40_000}


def test_a_transfer_has_no_category_to_move(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    make_account(chat, "Gopay", type_="ewallet", balance=0, alias="gopay")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "transfer",
                        "amount": 100_000,
                        "from_account": "bca",
                        "to_account": "gopay",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "topup gopay 100rb dari bca")["drafts"][0]
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    transaction_id = chat.get("/transactions").json()[0]["id"]

    chat.adapter.queue(
        tool(
            "propose_recategorise",
            {"transaction_id": transaction_id, "to_category": "Transport"},
        )
    )
    chat.adapter.queue(text("Transaksi ini tidak punya kategori."))

    assert send(chat, "pindahin ke transport")["drafts"] == []
    assert "tidak punya kategori" in tool_error(chat)


def test_an_unknown_source_category_lists_the_real_ones(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    expense(chat, 25_000, "Transport")

    chat.adapter.queue(
        tool("propose_recategorise", {"from_category": "Hiburan", "to_category": "Transport"})
    )
    chat.adapter.queue(text("Kategori itu belum ada."))

    assert send(chat, "gabung hiburan ke transport")["drafts"] == []

    # Named, so the model can offer the real ones rather than invent one.
    error = tool_error(chat)
    assert "Hiburan" in error and "Transport" in error


def test_moving_a_category_onto_itself_is_refused(chat):
    """Two words, one category: "ongkos" and "Transport" are the same row.

    The refusal names both sides, so the model can say what happened
    rather than offer a card that would move nothing.
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    expense(chat, 25_000, "Transport")

    chat.adapter.queue(
        tool("propose_recategorise", {"from_category": "ongkos", "to_category": "Transport"})
    )
    chat.adapter.queue(text("Itu kategori yang sama."))

    assert send(chat, "gabung transport ke transport")["drafts"] == []
    assert "kategori yang sama" in tool_error(chat)


def test_naming_both_a_transaction_and_a_category_is_refused(chat):
    """Two different acts. Guessing which one was meant is how AC04 breaks."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    expense(chat, 25_000, "Transport")

    items = chat.get("/transactions").json()

    chat.adapter.queue(
        tool(
            "propose_recategorise",
            {
                "transaction_id": items[0]["id"],
                "from_category": "Transport",
                "to_category": "Belanja",
            },
        )
    )
    chat.adapter.queue(text("Pilih salah satu."))

    assert send(chat, "pindahin")["drafts"] == []
    assert "Pilih salah satu" in tool_error(chat)


def test_another_users_transaction_cannot_be_moved(chat, engine, monkeypatch):
    """AC08: ownership is checked before anything is drafted."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    expense(chat, 25_000, "Transport")

    items = chat.get("/transactions").json()
    victim_id = items[0]["id"]

    from fastapi.testclient import TestClient

    from app.api import routes_chat
    from app.main import app

    intruder_adapter = FakeAdapter()

    with TestClient(app) as intruder:
        intruder.post(
            "/auth/register", json={"email": "intruder@example.com", "password": "sangat-rahasia-123"}
        ).raise_for_status()

        routes_chat.set_adapter(intruder_adapter)
        intruder_adapter.queue(
            tool("propose_recategorise", {"transaction_id": victim_id, "to_category": "Belanja"})
        )
        intruder_adapter.queue(text("Transaksi tidak ditemukan."))

        response = intruder.post("/chat/messages", json={"body": "pindahin"})
        assert response.status_code == 200
        assert response.json()["drafts"] == []
        results = [
            m for m in intruder_adapter.calls[-1]["messages"] if m["role"] == "tool"
        ]
        assert "tidak ditemukan" in results[-1]["content"]

    routes_chat.set_adapter(chat.adapter)

    # Untouched.
    assert spending(chat) == {"Transportasi": 25_000}


# ----------------------------------------------------------------------
# Finding the thing to move
# ----------------------------------------------------------------------


def test_find_transactions_names_the_category(chat):
    """Without it the model asked the user for a figure the ledger held."""
    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")
    expense(chat, 25_000, "Ongkos", account="cash")

    chat.adapter.queue(tool("find_transactions", {}))
    chat.adapter.queue(text("Ini transaksinya."))
    send(chat, "transaksi terakhir apa")

    sent = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][-1]["content"]
    assert "Transportasi" in sent
    assert "25000" in sent


def test_find_transactions_can_be_narrowed_to_one_category(chat):
    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")
    expense(chat, 25_000, "Ongkos", account="cash")
    expense(chat, 70_000, "Makan", account="cash")

    chat.adapter.queue(tool("find_transactions", {"category": "ongkos"}))
    chat.adapter.queue(text("Ini transaksinya."))
    send(chat, "transaksi ongkos mana")

    sent = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][-1]["content"]
    assert "Transportasi" in sent
    assert "Makan" not in sent


def test_a_merge_moves_legs_sitting_on_an_older_duplicate_spelling(chat, engine):
    """Folding the case stops new duplicates; it does not undo old ones.

    A ledger written before the fold can hold "Transportasi" and
    "transportasi" as two accounts, with the month's legs split between
    them. The merge has to collect both, which is why each leg carries
    the account it actually sits on rather than the draft naming one for
    all of them.
    """
    from sqlalchemy import select, update
    from sqlalchemy.orm import Session

    from app.models import Account, AccountType, Entry, User

    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")
    expense(chat, 25_000, "Ongkos", account="cash")
    expense(chat, 15_000, "Ongkos", account="cash")

    second = chat.get("/transactions").json()[0]["id"]

    with Session(engine, expire_on_commit=False) as db:
        owner = db.scalar(select(User).where(User.email == "chat@example.com"))
        duplicate = Account(
            user_id=owner.id,
            name="transportasi",
            type=AccountType.EXPENSE_CATEGORY,
            kind=AccountKind.EXPENSE,
            is_system=True,
        )
        db.add(duplicate)
        db.flush()

        original = db.scalar(
            select(Account).where(
                Account.user_id == owner.id,
                Account.name == "Transportasi",
                Account.type == AccountType.EXPENSE_CATEGORY,
            )
        )
        db.execute(
            update(Entry)
            .where(
                Entry.transaction_id == uuid.UUID(second),
                Entry.account_id == original.id,
            )
            .values(account_id=duplicate.id)
        )
        db.commit()

    # Split across two spellings, exactly as the report showed it.
    assert spending(chat) == {"Transportasi": 25_000, "transportasi": 15_000}

    chat.adapter.queue(
        tool("propose_recategorise", {"from_category": "transportasi", "to_category": "Makan"})
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "gabung ongkos ke makan")["drafts"][0]

    assert draft["payload"]["count"] == 2
    assert draft["payload"]["amount"] == 40_000

    # The legs really are on two different accounts, which is the whole
    # point of this test: one `from_account_id` for the draft would have
    # looked for half of them in the wrong place.
    assert len({m["from_account_id"] for m in draft["payload"]["moves"]}) == 2

    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200
    assert spending(chat) == {"Makan": 40_000}
    assert balances(chat)["Cash"] == 460_000


def test_a_refunded_purchase_merges_without_doubling_itself(chat):
    """A refund sits on its category as a credit, and must stay one.

    Moved as a size rather than a signed figure, the refund would travel
    as though it were a purchase: the old category ends at minus twice
    the refund instead of zero, and the new one is overstated by the
    same amount.
    """
    make_account(chat, "Cash", type_="cash", balance=500_000, alias="cash")

    expense(chat, 50_000, "Ongkos", account="cash")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "refund",
                        "amount": 20_000,
                        "to_account": "cash",
                        "category": "Ongkos",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    refund = send(chat, "ongkos 20rb dibalikin")["drafts"][0]
    assert chat.post(f"/chat/drafts/{refund['id']}/confirm").status_code == 200

    assert spending(chat) == {"Transportasi": 30_000}
    before = balances(chat)["Cash"]

    chat.adapter.queue(
        tool("propose_recategorise", {"from_category": "Ongkos", "to_category": "Makan"})
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "gabung ongkos ke makan")["drafts"][0]

    assert draft["payload"]["count"] == 2
    assert draft["payload"]["amount"] == 30_000

    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    assert spending(chat) == {"Makan": 30_000}
    assert balances(chat)["Cash"] == before
