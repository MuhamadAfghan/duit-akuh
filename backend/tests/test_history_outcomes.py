"""What the model is told about the cards already in the thread.

The history said only that *a* draft card appeared. Every card read the
same, so a purchase the user had saved and one they had abandoned were
indistinguishable — and when the next message mentioned a second
expense, the model proposed a batch holding both, re-offering money
that was already in the ledger.

Swiping that through would have posted the first purchase twice, and no
idempotency key would have stopped it: a new draft is a new operation,
which everywhere else is exactly what is wanted. So the fix is in what
the model is shown, not in another guard at the write.
"""

from __future__ import annotations

import pytest

from app.services.ai.fake import text, tool

from .conftest import make_account, requires_db, send

pytestmark = [requires_db, pytest.mark.integration]


def assistant_history(chat) -> str:
    """Everything the model was shown as its own earlier turns."""
    return " ".join(
        m["content"] or "" for m in chat.adapter.calls[-1]["messages"] if m["role"] == "assistant"
    )


def propose(chat, amount: int, category: str, message: str) -> dict:
    """Raise one expense draft through the chat, without confirming it."""
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": amount,
                        "from_account": "cash",
                        "category": category,
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))

    return send(chat, message)["drafts"][0]


def test_a_saved_card_is_marked_saved(chat):
    """The bug: a confirmed purchase looked exactly like a pending one."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    draft = propose(chat, 5_000, "Belanja", "fotocopy 5rb pake cash")
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    chat.adapter.queue(text("Baik."))
    send(chat, "tadi abis makan siang warteg 17rb pake cash")

    history = assistant_history(chat)
    assert "SUDAH DISIMPAN" in history
    assert "Rp5.000" in history, "the model has to know which item is done"
    assert "propose_" in history, "the tool-call evidence must survive"


def test_a_cancelled_card_is_marked_cancelled(chat):
    """The other half: an abandoned draft must not read as saved."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    draft = propose(chat, 5_000, "Belanja", "fotocopy 5rb pake cash")
    assert chat.post(f"/chat/drafts/{draft['id']}/cancel").status_code == 204

    chat.adapter.queue(text("Baik."))
    send(chat, "terus apa lagi")

    history = assistant_history(chat)
    assert "Dibatalkan" in history
    assert "SUDAH DISIMPAN" not in history


def test_a_pending_card_says_it_is_still_waiting(chat):
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")
    propose(chat, 5_000, "Belanja", "fotocopy 5rb pake cash")

    chat.adapter.queue(text("Baik."))
    send(chat, "terus apa lagi")

    history = assistant_history(chat)
    assert "menunggu konfirmasi" in history
    assert "SUDAH DISIMPAN" not in history


def test_a_saved_batch_names_its_entries(chat):
    """A batch is the shape the bug produced, so it has to digest too."""
    make_account(chat, "Cash", type_="cash", balance=860_000, alias="cash")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": 5_000,
                        "from_account": "cash",
                        "category": "Belanja",
                    },
                    {
                        "type": "expense",
                        "amount": 17_000,
                        "from_account": "cash",
                        "category": "Makan",
                    },
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "fotocopy 5rb dan makan 17rb pake cash")["drafts"][0]
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200

    chat.adapter.queue(text("Baik."))
    send(chat, "udah itu aja")

    history = assistant_history(chat)
    assert "2 transaksi" in history
    assert "Rp5.000" in history
    assert "Rp17.000" in history
    assert "SUDAH DISIMPAN" in history


def test_the_nudge_does_not_ask_for_the_whole_thread(chat):
    """The corrective round told the model to sweep up everything.

    When a reply claimed a draft without calling a tool, the backend
    sent a nudge saying to call propose_* "sekaligus semua itemnya".
    Re-reading the thread, the model took "semua" to mean every
    transaction anyone had ever mentioned in it — including ones it had
    already posted — and came back with a batch that re-offered money
    already in the ledger. Confirming that charged the first purchase
    twice.

    Verified against the real model: with the old wording the second
    message produced a four-entry batch, with this one a single entry.
    """
    from app.services.chat.orchestrator import _NUDGE

    assert "pesan-pesan sebelumnya" in _NUDGE, "the nudge must exclude earlier turns"
    assert "dua kali" in _NUDGE, "and say why: the money would be counted twice"
