"""The chat orchestrator, driven by a scripted adapter.

No network, no GPU, no API key. What is worth pinning down here is not
the happy path — it is what happens when the model misbehaves, because
the model is the one component that cannot be made reliable: bad
arguments, an ambiguous account, a tool that does not exist, a refusal
to stop calling tools, and the service being down entirely.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.services.ai.fake import outage, text, tool

from .conftest import PASSWORD, balances, make_account, requires_db, send

pytestmark = [requires_db, pytest.mark.integration]

# ----------------------------------------------------------------------
# Access
# ----------------------------------------------------------------------


def test_chat_requires_a_session(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        assert anon.get("/chat/messages").status_code == 401
        assert anon.post("/chat/messages", json={"body": "halo"}).status_code == 401


# ----------------------------------------------------------------------
# The thread persists (FR15)
# ----------------------------------------------------------------------


def test_thread_survives_and_accumulates(chat):
    chat.adapter.queue(text("Halo!"))
    send(chat, "halo")

    chat.adapter.queue(text("Siap."))
    send(chat, "oke")

    messages = chat.get("/chat/messages").json()
    bodies = [m["body"] for m in messages]

    assert bodies == ["halo", "Halo!", "oke", "Siap."]


def test_history_is_sent_to_the_model(chat):
    """ "the account I just mentioned" can only resolve with context."""
    chat.adapter.queue(text("Halo!"))
    send(chat, "pesan pertama")

    chat.adapter.queue(text("Oke."))
    send(chat, "pesan kedua")

    last_prompt = chat.adapter.calls[-1]["messages"]
    contents = [m["content"] for m in last_prompt]

    assert contents[0].startswith("Kamu asisten keuangan")
    assert "pesan pertama" in contents
    assert "pesan kedua" in contents


def test_each_users_thread_is_separate(chat, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    chat.adapter.queue(text("Halo!"))
    send(chat, "rahasia saya")

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "other@example.com", "password": PASSWORD}
        ).raise_for_status()
        assert other.get("/chat/messages").json() == []


# ----------------------------------------------------------------------
# Read tools
# ----------------------------------------------------------------------


def test_read_tool_runs_without_confirmation(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(tool("get_summary", {}))
    chat.adapter.queue(text("Saldo likuidmu Rp1.000.000."))

    result = send(chat, "saldo saya berapa")

    assert result["drafts"] == []
    assert "1.000.000" in result["reply"]

    # The tool's real output was fed back to the model.
    tool_messages = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"]
    assert '"liquid": 1000000' in tool_messages[0]["content"]


def test_tool_results_come_from_the_database_not_the_model(chat):
    """The model never supplies a figure; the backend computes it."""
    make_account(chat, "BCA", balance=777_000, alias="bca")

    chat.adapter.queue(tool("get_accounts", {}))
    chat.adapter.queue(text("ok"))

    send(chat, "kantong saya apa saja")

    tool_output = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]
    assert '"balance": 777000' in tool_output["content"]


# ----------------------------------------------------------------------
# Propose tools never write
# ----------------------------------------------------------------------


def test_propose_creates_a_draft_and_writes_nothing(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))

    result = send(chat, "makan 35rb pakai bca")

    assert len(result["drafts"]) == 1
    draft = result["drafts"][0]
    assert draft["status"] == "pending"
    assert draft["payload"]["amount"] == 35_000

    impact = {r["account"]: r for r in draft["impact"]}
    assert impact["BCA"]["before"] == 1_000_000
    assert impact["BCA"]["after"] == 965_000

    # Nothing posted.
    assert balances(chat)["BCA"] == 1_000_000


def test_confirming_a_draft_posts_exactly_what_was_shown(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "makan 35rb pakai bca")["drafts"][0]

    predicted = {r["account"]: r["after"] for r in draft["impact"]}

    response = chat.post(f"/chat/drafts/{draft['id']}/confirm")
    assert response.status_code == 200
    assert response.json()["replayed"] is False

    assert balances(chat)["BCA"] == predicted["BCA"] == 965_000


def test_confirming_twice_posts_once(chat):
    """AC13: a stale card tapped again must not duplicate."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "makan 35rb pakai bca")["drafts"][0]

    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200
    # Second tap: the draft is no longer pending.
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 404

    assert balances(chat)["BCA"] == 965_000


def test_cancelling_a_draft_leaves_the_balance_alone(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "makan 35rb pakai bca")["drafts"][0]

    assert chat.post(f"/chat/drafts/{draft['id']}/cancel").status_code == 204
    assert balances(chat)["BCA"] == 1_000_000
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 404


def test_cannot_confirm_another_users_draft(chat, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("draft"))
    draft = send(chat, "makan 35rb")["drafts"][0]

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "thief2@example.com", "password": PASSWORD}
        ).raise_for_status()
        assert other.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 404

    assert balances(chat)["BCA"] == 1_000_000


def test_transfer_through_chat_keeps_the_fee_separate(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    make_account(chat, "GoPay", "ewallet", alias="gopay")

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
                        "fee": 1_000,
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("draft"))
    draft = send(chat, "topup gopay 100rb dari bca, admin 1rb")["drafts"][0]

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    current = balances(chat)
    summary = chat.get("/summary").json()

    assert current["BCA"] == 899_000
    assert current["GoPay"] == 100_000
    assert summary["expense_total"] == 1_000
    assert summary["income_total"] == 0


# ----------------------------------------------------------------------
# The model misbehaving
# ----------------------------------------------------------------------


def test_ambiguous_account_produces_a_question_not_a_draft(chat):
    """AC04: two accounts match 'BCA', so nothing may be posted or guessed."""
    make_account(chat, "BCA Tahapan", balance=1_000_000, alias="tahapan")
    make_account(chat, "BCA Bisnis", balance=500_000, alias="bisnis")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "BCA"}]},
        )
    )
    chat.adapter.queue(text("BCA yang mana: Tahapan atau Bisnis?"))

    result = send(chat, "makan 35rb pakai bca")

    assert result["drafts"] == []
    assert "mana" in result["reply"].lower()

    error = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]
    assert "BCA Tahapan" in error["content"]
    assert "BCA Bisnis" in error["content"]


def test_unknown_account_produces_an_error_not_a_draft(chat):
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 1_000, "from_account": "Jenius"}]},
        )
    )
    chat.adapter.queue(text("Kantong Jenius belum ada."))

    assert send(chat, "bayar 1rb pakai jenius")["drafts"] == []


@pytest.mark.parametrize(
    "amount", [35_000.5, 0.1, "35.000", "1,5", "banyak", -1_000, 0, None, {"nominal": 1}]
)
def test_a_bad_amount_from_the_model_is_refused(chat, amount):
    """Model output is data, not instruction - every field is re-validated."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": amount, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("Nominalnya kurang jelas."))

    result = send(chat, "catat sesuatu")

    assert result["drafts"] == []
    assert balances(chat)["BCA"] == 1_000_000


def test_a_digit_string_amount_is_accepted(chat):
    """Deliberately more lenient than the REST API, which rejects strings.

    The REST API is consumed by our own PWA, which we can make send
    integers. This path consumes model output, which we cannot control,
    and "35000" is lossless and common from an LLM - refusing it would
    fail the user for nothing. Anything actually ambiguous ("35.000",
    "1,5") still raises.
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": "35000", "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("draft"))

    drafts = send(chat, "makan 35rb")["drafts"]

    assert len(drafts) == 1
    assert drafts[0]["payload"]["amount"] == 35_000, "stored as an int, not a string"


def test_an_unknown_tool_does_not_crash_the_turn(chat):
    chat.adapter.queue(tool("delete_everything", {"confirm": True}))
    chat.adapter.queue(text("Aku tidak bisa melakukan itu."))

    result = send(chat, "hapus semua")

    assert result["degraded"] is False
    error = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]
    assert "tidak tersedia" in error["content"]


def test_a_model_that_never_stops_calling_tools_is_cut_off(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    from app.services.chat.orchestrator import MAX_TOOL_ROUNDS

    for _ in range(MAX_TOOL_ROUNDS + 5):
        chat.adapter.queue(tool("get_summary", {}))

    result = send(chat, "loop please")

    # Bounded: it stopped rather than holding a GPU slot forever.
    assert len(chat.adapter.calls) == MAX_TOOL_ROUNDS
    assert result["reply"]


def test_too_many_transactions_in_one_message_is_refused(chat):
    make_account(chat, "BCA", balance=10_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {"type": "expense", "amount": 1_000, "from_account": "bca"} for _ in range(11)
                ]
            },
        )
    )
    chat.adapter.queue(text("Terlalu banyak."))

    assert send(chat, "catat 11 transaksi")["drafts"] == []


# ----------------------------------------------------------------------
# The AI being down (AC09, AC22)
# ----------------------------------------------------------------------


def test_an_outage_degrades_instead_of_failing(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    chat.adapter.queue(outage())

    result = send(chat, "makan 35rb")

    assert result["degraded"] is True
    assert "manual" in result["reply"].lower()
    # The user's message was still kept.
    assert [m["body"] for m in chat.get("/chat/messages").json()][0] == "makan 35rb"


def test_manual_entry_still_works_during_an_outage(chat):
    """AC22: the ledger does not depend on the model being up."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    chat.adapter.queue(outage())
    send(chat, "makan 35rb")

    account_id = chat.get("/accounts").json()[0]["id"]
    response = chat.post(
        "/transactions",
        headers={"Idempotency-Key": f"manual-{uuid.uuid4()}"},
        json={"type": "expense", "amount": 35_000, "from_account_id": account_id},
    )

    assert response.status_code == 201
    assert balances(chat)["BCA"] == 965_000


# ----------------------------------------------------------------------
# AI request logging (PRD section 13)
# ----------------------------------------------------------------------


def test_ai_requests_are_logged_without_prompt_contents(chat, engine):
    from sqlalchemy.orm import Session as DbSession

    from app.models import AiRequestLog

    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    chat.adapter.queue(tool("get_summary", {}))
    chat.adapter.queue(text("Selesai."))
    send(chat, "rahasia-yang-tidak-boleh-bocor 35rb")

    with DbSession(bind=engine) as db:
        logs = db.query(AiRequestLog).all()

        assert len(logs) == 2, "one per model round"
        assert {log.status for log in logs} == {"ok"}
        assert any(log.tool_calls == ["get_summary"] for log in logs)

        # Tool names only - arguments carry amounts and account names.
        blob = " ".join(str(log.__dict__) for log in logs)
        assert "rahasia-yang-tidak-boleh-bocor" not in blob


def test_an_outage_is_logged_as_an_error(chat, engine):
    from sqlalchemy.orm import Session as DbSession

    from app.models import AiRequestLog

    chat.adapter.queue(outage("GPU penuh"))
    send(chat, "halo")

    with DbSession(bind=engine) as db:
        log = db.query(AiRequestLog).one()

        assert log.status == "error"
        assert "GPU penuh" in log.error
        assert log.latency_ms is not None


def test_history_shows_that_tools_were_used(chat):
    """Regression guard for a failure seen against the real model.

    History used to contain only the assistant's prose. With no evidence
    that tools were ever called, the model copied the pattern: it replied
    "Draft transaksi: ..." in text without calling propose_*, so the user
    got a message claiming a draft that did not exist. Card turns now say
    explicitly that a tool produced them.
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    send(chat, "makan 35rb pakai bca")

    chat.adapter.queue(text("Baik."))
    send(chat, "pesan berikutnya")

    history = " ".join(
        m["content"] or "" for m in chat.adapter.calls[-1]["messages"] if m["role"] == "assistant"
    )

    assert "propose_" in history, "history must show the draft came from a tool call"


def test_the_model_is_told_todays_date(chat):
    """Regression guard for a real mis-dating.

    Asked to record "kemarin", the model emitted occurred_on 2023-10-25 —
    three years off — because nothing in the prompt said what day it is.
    It has no clock, so the date has to be supplied.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    chat.adapter.queue(text("Halo."))
    send(chat, "halo")

    system = chat.adapter.calls[-1]["messages"][0]
    today = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d")

    assert system["role"] == "system"
    assert today in system["content"], "the prompt must carry today's date"
    assert "Asia/Jakarta" in system["content"]


def test_a_prose_only_draft_claim_triggers_one_retry(chat):
    """The model sometimes says "draft sudah dibuat" without calling a tool.

    Passing that through would tell the user their transaction was
    recorded when nothing exists. One corrective round is given; if it
    then calls the tool, the draft is real.
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    # Round 1: prose only, no tool call.
    chat.adapter.queue(text("Draft transaksi pengeluaran 35.000 dari BCA sudah dibuat."))
    # The nudge round: now it complies.
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
            content="Ini draftnya.",
        )
    )

    result = send(chat, "makan 35rb pakai bca")

    assert len(result["drafts"]) == 1
    assert result["drafts"][0]["payload"]["amount"] == 35_000

    nudge = chat.adapter.calls[-1]["messages"][-1]
    assert nudge["role"] == "user"
    assert "tidak memanggil tool" in nudge["content"]


def test_a_persistent_prose_claim_is_replaced_with_an_honest_reply(chat):
    """If it will not comply twice, say so rather than repeat the claim."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(text("Draft sudah dibuat dan tersimpan."))
    chat.adapter.queue(text("Sudah saya catat kok."))

    result = send(chat, "makan 35rb pakai bca")

    assert result["drafts"] == []
    assert "belum berhasil" in result["reply"]
    assert "sudah dibuat" not in result["reply"].lower()
    assert balances(chat)["BCA"] == 1_000_000


def test_an_ordinary_answer_does_not_trigger_a_retry(chat):
    """A reply with no draft claim must not cost an extra model round."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(tool("get_summary", {}))
    chat.adapter.queue(text("Saldo likuidmu Rp1.000.000."))

    result = send(chat, "saldo berapa")

    assert len(chat.adapter.calls) == 2, "no corrective round for a normal answer"
    assert "1.000.000" in result["reply"]


# ----------------------------------------------------------------------
# Goals through chat (FR07, AC05)
# ----------------------------------------------------------------------


def test_creating_a_goal_through_chat_needs_confirmation(chat):
    chat.adapter.queue(tool("propose_goal", {"name": "Laptop", "target_amount": 15_000_000}))
    chat.adapter.queue(text("Ini draft targetnya."))

    result = send(chat, "bikin target laptop 15 juta")

    assert len(result["drafts"]) == 1
    assert chat.get("/goals").json() == [], "nothing saved before confirmation"

    chat.post(f"/chat/drafts/{result['drafts'][0]['id']}/confirm").raise_for_status()

    goals = chat.get("/goals").json()
    assert len(goals) == 1
    assert goals[0]["name"] == "Laptop"
    assert goals[0]["target_amount"] == 15_000_000


def test_allocating_through_chat_does_not_create_money(chat):
    """AC05 again, this time via the conversational path."""
    make_account(chat, "BCA", balance=5_000_000, alias="bca")
    chat.post("/goals", json={"name": "Laptop", "target_amount": 15_000_000}).raise_for_status()

    before = chat.get("/summary").json()

    chat.adapter.queue(
        tool(
            "propose_allocation",
            {"goal_name": "Laptop", "account": "bca", "amount": 2_000_000},
        )
    )
    chat.adapter.queue(text("Ini draft alokasinya."))
    draft = send(chat, "alokasikan 2 juta dari bca ke laptop")["drafts"][0]

    assert chat.get("/summary").json()["allocated"] == 0, "not saved yet"

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    after = chat.get("/summary").json()

    assert after["liquid"] == before["liquid"] == 5_000_000
    assert after["net_worth"] == before["net_worth"]
    assert after["allocated"] == 2_000_000
    assert after["free_to_spend"] == 3_000_000


def test_an_allocation_above_the_balance_never_becomes_a_draft(chat):
    """Validated while drafting, so the card cannot promise the impossible."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    chat.post("/goals", json={"name": "Laptop", "target_amount": 15_000_000}).raise_for_status()

    chat.adapter.queue(
        tool(
            "propose_allocation",
            {"goal_name": "Laptop", "account": "bca", "amount": 5_000_000},
        )
    )
    chat.adapter.queue(text("Saldonya tidak cukup."))

    result = send(chat, "alokasikan 5 juta ke laptop")

    assert result["drafts"] == []
    error = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]
    assert "1000000" in error["content"], "tells the model the real headroom"


def test_an_ambiguous_goal_name_asks_rather_than_guessing(chat):
    make_account(chat, "BCA", balance=5_000_000, alias="bca")
    for name in ("Laptop Kerja", "Laptop Gaming"):
        chat.post("/goals", json={"name": name, "target_amount": 10_000_000}).raise_for_status()

    chat.adapter.queue(
        tool(
            "propose_allocation",
            {"goal_name": "Laptop", "account": "bca", "amount": 1_000_000},
        )
    )
    chat.adapter.queue(text("Laptop yang mana?"))

    result = send(chat, "alokasikan 1 juta ke laptop")

    assert result["drafts"] == []
    error = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]
    assert "Laptop Kerja" in error["content"]
    assert "Laptop Gaming" in error["content"]


def test_a_draft_goes_stale_when_the_balance_moves_underneath_it(chat):
    """FR15: a card must not post something its preview no longer describes."""
    account_id = make_account(chat, "BCA", balance=3_000_000, alias="bca")["id"]
    chat.post("/goals", json={"name": "Laptop", "target_amount": 15_000_000}).raise_for_status()

    chat.adapter.queue(
        tool(
            "propose_allocation",
            {"goal_name": "Laptop", "account": "bca", "amount": 3_000_000},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "alokasikan 3 juta ke laptop")["drafts"][0]

    # Spend most of it before confirming.
    chat.post(
        "/transactions",
        headers={"Idempotency-Key": f"spend-{uuid.uuid4()}"},
        json={"type": "expense", "amount": 2_500_000, "from_account_id": account_id},
    ).raise_for_status()

    response = chat.post(f"/chat/drafts/{draft['id']}/confirm")

    assert response.status_code == 409
    assert chat.get("/summary").json()["allocated"] == 0


# ----------------------------------------------------------------------
# Simulation through chat (FR11, AC07)
# ----------------------------------------------------------------------


def test_a_simulation_needs_no_confirmation_and_changes_nothing(chat):
    make_account(chat, "BCA", balance=10_000_000, alias="bca")

    before = chat.get("/summary").json()

    chat.adapter.queue(
        tool(
            "run_simulation",
            {
                "kind": "deposit",
                "principal": 10_000_000,
                "annual_rate_percent": "4",
                "months": 6,
                "tax_percent": "20",
            },
        )
    )
    chat.adapter.queue(text("Bunga bersihnya Rp160.000."))

    result = send(chat, "kalau 10 juta didepositokan 4% 6 bulan dapat berapa?")

    assert result["drafts"] == [], "a calculator raises no draft"
    assert chat.get("/summary").json() == before

    output = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]
    assert '"net_interest": 160000' in output["content"]


def test_an_unknown_tax_rate_warns_the_model_not_to_claim_certainty(chat):
    chat.adapter.queue(
        tool(
            "run_simulation",
            {
                "kind": "deposit",
                "principal": 10_000_000,
                "annual_rate_percent": "4",
                "months": 6,
            },
        )
    )
    chat.adapter.queue(text("Perkiraannya Rp200.000, tapi pajaknya belum dihitung."))

    send(chat, "deposito 10 juta 4% 6 bulan")

    output = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]
    assert '"complete": false' in output["content"]
    assert "belum lengkap" in output["content"]


def test_the_saving_simulation_accepts_months_as_well_as_periods(chat):
    """Regression guard for a real failure.

    The model called run_simulation with "months" where the schema says
    "periods". The tool refused, and the model then did the arithmetic
    itself - right by luck that time, but inventing figures is exactly
    what the PRD forbids it to do.
    """
    chat.adapter.queue(
        tool(
            "run_simulation",
            {"kind": "saving", "target": 15_000_000, "initial": 3_000_000, "months": 6},
        )
    )
    chat.adapter.queue(text("Rp2 juta per bulan."))

    send(chat, "ngumpulin 15 juta dalam 6 bulan, dana awal 3 juta")

    output = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]

    assert '"per_period": 2000000' in output["content"]
    assert "error" not in output["content"]


def test_a_failed_simulation_tells_the_model_not_to_compute_it_itself(chat):
    chat.adapter.queue(tool("run_simulation", {"kind": "saving", "target": 15_000_000}))
    chat.adapter.queue(text("Berapa lama mau menabungnya?"))

    send(chat, "ngumpulin 15 juta")

    output = [m for m in chat.adapter.calls[-1]["messages"] if m["role"] == "tool"][0]

    assert "Jangan hitung sendiri" in output["content"]


# ----------------------------------------------------------------------
# Rate limiting and queueing (PRD section 13)
# ----------------------------------------------------------------------


def test_too_many_messages_are_rate_limited_with_a_retryable_status(chat):
    from app.services.ai.limits import RATE_LIMIT

    for _ in range(RATE_LIMIT + 2):
        chat.adapter.queue(text("ok"))

    codes = [
        chat.post("/chat/messages", json={"body": "halo"}).status_code
        for _ in range(RATE_LIMIT + 2)
    ]

    assert codes[0] == 200
    assert 429 in codes, f"expected a limit after {RATE_LIMIT} messages, got {codes}"

    blocked = chat.post("/chat/messages", json={"body": "halo"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "ai_rate_limited"
    # Tells the client when to come back rather than making it guess.
    assert blocked.headers["retry-after"] == "60"


def test_a_busy_service_returns_503_with_retry_after(chat, monkeypatch):
    """Cloudflare 524s past 100s, so waiting forever is not an option."""
    from app.api import routes_chat
    from app.services.ai.limits import AiGate

    # One slot, already taken, and no patience.
    busy = AiGate(max_concurrency=1, timeout=0.01)
    monkeypatch.setattr(routes_chat, "gate", busy)

    import asyncio

    async def occupy():
        async with busy.slot(uuid.uuid4()):
            await asyncio.sleep(5)

    loop = asyncio.new_event_loop()
    task = loop.create_task(occupy())
    loop.run_until_complete(asyncio.sleep(0.01))

    try:
        chat.adapter.queue(text("ok"))
        response = chat.post("/chat/messages", json={"body": "halo"})

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "ai_busy"
        assert response.headers["retry-after"] == "10"
        # The message points at the manual path, as AC22 requires.
        assert "manual" in response.json()["detail"]["message"].lower()
    finally:
        task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        loop.close()


def test_reads_are_not_rate_limited(chat):
    """Only the AI path is scarce; reading the thread is not."""
    from app.services.ai.limits import RATE_LIMIT

    for _ in range(RATE_LIMIT + 2):
        chat.adapter.queue(text("ok"))
    for _ in range(RATE_LIMIT + 2):
        chat.post("/chat/messages", json={"body": "halo"})

    assert chat.get("/chat/messages").status_code == 200
    assert chat.get("/summary").status_code == 200


# ----------------------------------------------------------------------
# Streaming
# ----------------------------------------------------------------------


def stream(chat, body: str) -> list[dict]:
    """Collect the NDJSON events from one streamed turn."""
    with chat.stream("POST", "/chat/messages/stream", json={"body": body}) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("application/x-ndjson")

        return [json.loads(line) for line in response.iter_lines() if line.strip()]


def test_a_streamed_turn_ends_with_done(chat):
    chat.adapter.queue(text("Halo!"))

    events = stream(chat, "halo")

    assert events[-1]["type"] == "done"
    assert events[-1]["reply"] == "Halo!"
    assert events[-1]["degraded"] is False


def test_content_arrives_as_tokens_before_the_final_reply(chat):
    chat.adapter.queue(text("Saldo likuidmu Rp1.000.000."))

    events = stream(chat, "saldo berapa")
    tokens = [e["text"] for e in events if e["type"] == "token"]

    assert len(tokens) > 1, "the reply should arrive in pieces, not one lump"
    assert "".join(tokens) == "Saldo likuidmu Rp1.000.000."


def test_tool_calls_are_announced_so_the_wait_is_explicable(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(tool("get_summary", {}))
    chat.adapter.queue(text("Rp1.000.000."))

    events = stream(chat, "saldo berapa")

    assert [e["name"] for e in events if e["type"] == "tool"] == ["get_summary"]


def test_a_draft_is_announced_as_soon_as_it_exists(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))

    events = stream(chat, "makan 35rb pakai bca")

    draft_events = [e for e in events if e["type"] == "draft"]
    assert len(draft_events) == 1

    done = events[-1]
    assert done["drafts"][0]["id"] == draft_events[0]["draft_id"]
    assert done["drafts"][0]["payload"]["amount"] == 35_000


def test_narration_alongside_a_tool_call_is_retracted(chat):
    """Text produced with a tool call is the model describing a plan.

    Tokens are forwarded the moment they arrive, so narration cannot be
    withheld - by the time we know a tool call follows it has already
    gone out. A `reset` event tells the client to drop what it showed,
    rather than leave a bubble claiming something happened before it
    did.
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
            content="Sebentar, saya buatkan draftnya...",
        )
    )
    chat.adapter.queue(text("Selesai."))

    events = stream(chat, "makan 35rb pakai bca")
    kinds = [e["type"] for e in events]

    assert "reset" in kinds, "narration must be retracted"
    # Everything streamed after the reset is the real answer.
    after_reset = kinds.index("reset")
    final = "".join(e["text"] for e in events[after_reset:] if e["type"] == "token")

    assert final == "Selesai."
    assert events[-1]["reply"] == "Selesai."


def test_an_outage_still_ends_the_stream_properly(chat):
    chat.adapter.queue(outage())

    events = stream(chat, "halo")
    done = events[-1]

    assert done["type"] == "done"
    assert done["degraded"] is True
    assert "manual" in done["reply"].lower()


def test_the_streaming_endpoint_is_rate_limited_too(chat):
    from app.services.ai.limits import RATE_LIMIT

    for _ in range(RATE_LIMIT + 2):
        chat.adapter.queue(text("ok"))
    for _ in range(RATE_LIMIT):
        chat.post("/chat/messages", json={"body": "halo"})

    response = chat.post("/chat/messages/stream", json={"body": "halo"})

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "ai_rate_limited"


def test_streaming_requires_a_session(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        assert anon.post("/chat/messages/stream", json={"body": "x"}).status_code == 401


def test_a_streamed_turn_is_persisted_like_any_other(chat):
    chat.adapter.queue(text("Halo!"))
    stream(chat, "halo lewat stream")

    bodies = [m["body"] for m in chat.get("/chat/messages").json()]

    assert bodies == ["halo lewat stream", "Halo!"]


def test_the_model_is_shown_which_wallets_exist(chat):
    """Regression guard for a benchmark finding.

    Without the list the model invented account names: asked to spend
    "pakai cc" it sent "credit_card", substituting the type for the
    name, and every card case in the benchmark failed.
    """
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    make_account(chat, "CC BCA", "credit_card", alias="cc")

    chat.adapter.queue(text("Halo."))
    send(chat, "halo")

    system = chat.adapter.calls[-1]["messages"][0]["content"]

    assert "BCA (bank, alias: bca)" in system
    assert "CC BCA (credit_card, alias: cc)" in system
    assert "jenis kantong" in system, "and told not to use the type as a name"


def test_archived_wallets_are_not_offered_to_the_model(chat):
    account = make_account(chat, "Dompet lama", "cash", balance=0)
    chat.patch(f"/accounts/{account['id']}", json={"is_archived": True}).raise_for_status()

    chat.adapter.queue(text("Halo."))
    send(chat, "halo")

    assert "Dompet lama" not in chat.adapter.calls[-1]["messages"][0]["content"]


# ----------------------------------------------------------------------
# Revising a draft (FR05): the fix for a model that got one field wrong.


def _expense_draft(chat, amount=35_000, wallet="bca"):
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": amount, "from_account": wallet}]},
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    return send(chat, f"makan {amount} pakai {wallet}")["drafts"][0]


def test_revising_an_amount_recomputes_the_impact(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    response = chat.post(f"/chat/drafts/{draft['id']}/revise", json={"patch": {"amount": 95_000}})
    assert response.status_code == 200, response.text

    revised = response.json()
    assert revised["payload"]["amount"] == 95_000

    # The figures must come from the ledger, not from the old card with
    # a new number pasted in.
    after = {r["account"]: r["after"] for r in revised["impact"]}
    assert after["BCA"] == 905_000


def test_a_revision_replaces_the_draft_so_the_old_id_cannot_post(chat):
    """The id the client was holding must stop working, or a confirm
    already in flight would post the figures the user just rejected."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    revised = chat.post(
        f"/chat/drafts/{draft['id']}/revise", json={"patch": {"amount": 95_000}}
    ).json()

    assert revised["id"] != draft["id"]
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 404

    assert chat.post(f"/chat/drafts/{revised['id']}/confirm").status_code == 200
    assert balances(chat)["BCA"] == 905_000


def test_revising_writes_nothing_until_confirmed(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    chat.post(f"/chat/drafts/{draft['id']}/revise", json={"patch": {"amount": 95_000}})

    assert balances(chat)["BCA"] == 1_000_000


def test_a_revision_can_move_the_entry_to_another_wallet(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    gopay = make_account(chat, "GoPay", "ewallet", balance=200_000)
    draft = _expense_draft(chat)

    revised = chat.post(
        f"/chat/drafts/{draft['id']}/revise", json={"patch": {"from_account_id": gopay["id"]}}
    ).json()

    assert chat.post(f"/chat/drafts/{revised['id']}/confirm").status_code == 200

    money = balances(chat)
    assert money["GoPay"] == 165_000
    assert money["BCA"] == 1_000_000


def test_the_revised_card_is_what_the_thread_shows(chat):
    """One card per proposal. Editing twice must not leave the thread
    with a trail of cancelled cards."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    first = chat.post(
        f"/chat/drafts/{draft['id']}/revise", json={"patch": {"amount": 95_000}}
    ).json()
    second = chat.post(
        f"/chat/drafts/{first['id']}/revise", json={"patch": {"amount": 40_000}}
    ).json()

    cards = [m["draft"] for m in chat.get("/chat/messages").json() if m["draft"]]
    assert [c["id"] for c in cards] == [second["id"]]
    assert cards[0]["payload"]["amount"] == 40_000


def test_an_unknown_field_is_refused_rather_than_ignored(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    response = chat.post(f"/chat/drafts/{draft['id']}/revise", json={"patch": {"ammount": 95_000}})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_patch"

    # Still pending: a refused patch must change nothing.
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200


def test_a_revision_cannot_reach_another_users_wallet(chat, engine, monkeypatch):
    """AC08: ownership is checked on the id, not assumed from the draft."""
    import uuid as _uuid

    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    response = chat.post(
        f"/chat/drafts/{draft['id']}/revise",
        json={"patch": {"from_account_id": str(_uuid.uuid4())}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "account_not_found"


def test_a_revision_that_changes_nothing_is_refused(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    response = chat.post(f"/chat/drafts/{draft['id']}/revise", json={"patch": {"amount": 35_000}})
    assert response.status_code == 422


def test_a_non_integer_amount_is_refused(chat):
    """FR03: money never becomes a float, not even on the way in."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    draft = _expense_draft(chat)

    response = chat.post(f"/chat/drafts/{draft['id']}/revise", json={"patch": {"amount": 95_000.5}})
    assert response.status_code == 422


def test_only_money_drafts_can_be_revised(chat):
    """A budget's payload has different rules; one patch format does not
    fit every kind, and pretending it does drops fields silently."""
    chat.adapter.queue(tool("propose_budget", {"category": "makan", "amount": 500_000}))
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "budget makan 500rb")["drafts"][0]

    response = chat.post(f"/chat/drafts/{draft['id']}/revise", json={"patch": {"amount": 600_000}})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "kind_not_revisable"


# ----------------------------------------------------------------------
# Replying to a turn.


def _thread(chat) -> list[dict]:
    return chat.get("/chat/messages").json()


def test_a_reply_carries_the_quoted_turn_to_the_client(chat):
    chat.adapter.queue(text("Bebas pakai lu Rp2.340.000."))
    send(chat, "uang bebas pakai berapa?")

    answer = next(m for m in _thread(chat) if m["role"] == "assistant")

    chat.adapter.queue(text("Belum, itu belum termasuk tagihan kartu."))
    chat.post(
        "/chat/messages",
        json={"body": "udah termasuk tagihan kartu?", "reply_to_id": answer["id"]},
    ).raise_for_status()

    reply = _thread(chat)[-2]
    assert reply["body"] == "udah termasuk tagihan kartu?"
    assert reply["reply_to"]["id"] == answer["id"]
    assert reply["reply_to"]["role"] == "assistant"
    assert reply["reply_to"]["excerpt"] == "Bebas pakai lu Rp2.340.000."


def test_the_model_is_told_what_was_replied_to(chat):
    """Without the quote a short "yang itu" is unanswerable: the model
    has no way to know which of ten earlier answers was meant."""
    chat.adapter.queue(text("Bebas pakai lu Rp2.340.000."))
    send(chat, "uang bebas pakai berapa?")

    answer = next(m for m in _thread(chat) if m["role"] == "assistant")

    chat.adapter.queue(text("Belum."))
    chat.post(
        "/chat/messages", json={"body": "yang itu gimana?", "reply_to_id": answer["id"]}
    ).raise_for_status()

    sent = chat.adapter.calls[-1]["messages"]
    quoting = [m for m in sent if m["role"] == "user" and "Membalas" in (m["content"] or "")]

    assert quoting, sent
    assert "Bebas pakai lu Rp2.340.000." in quoting[-1]["content"]
    assert "yang itu gimana?" in quoting[-1]["content"]


def test_a_long_quote_is_cut_before_it_reaches_the_model(chat):
    """The context window is 24,576 tokens for prompt and output
    together; quoting a whole answer back would spend it on repetition."""
    chat.adapter.queue(text("A" * 900))
    send(chat, "jelasin panjang lebar")

    answer = next(m for m in _thread(chat) if m["role"] == "assistant")

    chat.adapter.queue(text("Oke."))
    chat.post(
        "/chat/messages", json={"body": "ringkas dong", "reply_to_id": answer["id"]}
    ).raise_for_status()

    reply = _thread(chat)[-2]
    assert len(reply["reply_to"]["excerpt"]) < 200
    assert reply["reply_to"]["excerpt"].endswith("…")


def test_cannot_quote_a_message_that_does_not_exist(chat):
    response = chat.post("/chat/messages", json={"body": "halo", "reply_to_id": str(uuid.uuid4())})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "message_not_found"


def test_cannot_quote_another_users_message(chat, engine, monkeypatch):
    """AC08: a quote is a read of someone's thread, so it is gated like
    every other read."""
    from fastapi.testclient import TestClient

    from app.main import app

    chat.adapter.queue(text("Rahasia."))
    send(chat, "berapa saldo gua?")
    mine = next(m for m in _thread(chat) if m["role"] == "assistant")

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "lain@example.com", "password": PASSWORD}
        ).raise_for_status()

        response = other.post(
            "/chat/messages", json={"body": "itu apa?", "reply_to_id": mine["id"]}
        )
        assert response.status_code == 404


def test_a_refused_quote_writes_no_message(chat):
    """The id is checked before the turn starts, so a bad reference
    costs nothing - no stored message, no call to the model."""
    before = len(_thread(chat))

    chat.post("/chat/messages", json={"body": "halo", "reply_to_id": str(uuid.uuid4())})

    assert len(_thread(chat)) == before
    assert chat.adapter.calls == []


# ----------------------------------------------------------------------
# Named threads. One conversation per user became several (FR14, FR15).


def _threads(chat, **params) -> list[dict]:
    response = chat.get("/chat/conversations", params=params)
    response.raise_for_status()
    return response.json()


def test_a_fresh_account_lands_in_a_thread_without_choosing_one(chat):
    """The unique constraint is gone; what it protected is not. Nobody
    should have to create a conversation before they can type."""
    chat.adapter.queue(text("Halo."))
    send(chat, "halo")

    threads = _threads(chat)
    assert len(threads) == 1
    assert threads[0]["preview"] == "Halo."


def test_the_first_message_names_the_thread(chat):
    chat.adapter.queue(text("Oke."))
    send(chat, "rencana beli laptop akhir tahun")

    assert _threads(chat)[0]["title"] == "rencana beli laptop akhir tahun"


def test_a_long_first_message_is_clipped_into_a_title(chat):
    chat.adapter.queue(text("Oke."))
    send(chat, "tolong bantu gua " + "rapiin budget bulanan " * 10)

    title = _threads(chat)[0]["title"]
    assert len(title) <= 49
    assert title.endswith("…")


def test_threads_do_not_leak_into_each_other(chat):
    chat.adapter.queue(text("Jawaban pertama."))
    send(chat, "pertanyaan pertama")

    second = chat.post("/chat/conversations").json()

    chat.adapter.queue(text("Jawaban kedua."))
    chat.post(
        "/chat/messages", json={"body": "pertanyaan kedua", "conversation_id": second["id"]}
    ).raise_for_status()

    here = chat.get("/chat/messages", params={"conversation_id": second["id"]}).json()
    bodies = [m["body"] for m in here]

    assert "pertanyaan kedua" in bodies
    assert "pertanyaan pertama" not in bodies


def test_the_model_only_sees_the_thread_it_is_answering_in(chat):
    """Context is per thread. Carrying one conversation's history into
    another is both wrong and expensive against a 24,576-token window."""
    chat.adapter.queue(text("Rahasia dari thread lama."))
    send(chat, "catatan lama")

    second = chat.post("/chat/conversations").json()

    chat.adapter.queue(text("Oke."))
    chat.post(
        "/chat/messages", json={"body": "halo", "conversation_id": second["id"]}
    ).raise_for_status()

    sent = json.dumps(chat.adapter.calls[-1]["messages"], ensure_ascii=False)
    assert "catatan lama" not in sent
    assert "Rahasia dari thread lama" not in sent


def test_a_new_turn_without_an_id_goes_to_the_most_recent_thread(chat):
    chat.adapter.queue(text("Satu."))
    send(chat, "pertama")

    second = chat.post("/chat/conversations").json()
    chat.adapter.queue(text("Dua."))
    chat.post(
        "/chat/messages", json={"body": "kedua", "conversation_id": second["id"]}
    ).raise_for_status()

    # No id this time: it must continue where the user last was.
    chat.adapter.queue(text("Tiga."))
    send(chat, "ketiga")

    bodies = [m["body"] for m in chat.get("/chat/messages").json()]
    assert "ketiga" in bodies
    assert "pertama" not in bodies


def test_renaming_a_thread(chat):
    chat.adapter.queue(text("Oke."))
    send(chat, "catat makan")

    thread = _threads(chat)[0]
    response = chat.patch(
        f"/chat/conversations/{thread['id']}", json={"title": "  Belanja Oktober  "}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Belanja Oktober"


def test_a_blank_name_is_refused(chat):
    chat.adapter.queue(text("Oke."))
    send(chat, "catat makan")

    thread = _threads(chat)[0]
    response = chat.patch(f"/chat/conversations/{thread['id']}", json={"title": "   "})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_title"


def test_pinned_threads_sort_above_more_recent_ones(chat):
    chat.adapter.queue(text("Satu."))
    send(chat, "pertama")
    first = _threads(chat)[0]["id"]

    second = chat.post("/chat/conversations").json()
    chat.adapter.queue(text("Dua."))
    chat.post(
        "/chat/messages", json={"body": "kedua", "conversation_id": second["id"]}
    ).raise_for_status()

    assert [t["id"] for t in _threads(chat)] == [second["id"], first]

    chat.patch(f"/chat/conversations/{first}", json={"is_pinned": True}).raise_for_status()

    assert [t["id"] for t in _threads(chat)] == [first, second["id"]]


def test_archiving_hides_a_thread_and_drops_its_pin(chat):
    chat.adapter.queue(text("Oke."))
    send(chat, "catat makan")
    thread = _threads(chat)[0]["id"]

    chat.patch(f"/chat/conversations/{thread}", json={"is_pinned": True}).raise_for_status()
    chat.patch(f"/chat/conversations/{thread}", json={"is_archived": True}).raise_for_status()

    assert _threads(chat) == []

    archived = _threads(chat, include_archived=True)
    assert [t["id"] for t in archived] == [thread]
    # Still pinned, it would jump the list the moment it came back.
    assert archived[0]["is_pinned"] is False


def test_an_archived_thread_can_still_be_read_and_answered(chat):
    """Archiving takes a thread out of the list. It does not seal it."""
    chat.adapter.queue(text("Oke."))
    send(chat, "catat makan")
    thread = _threads(chat)[0]["id"]

    chat.patch(f"/chat/conversations/{thread}", json={"is_archived": True}).raise_for_status()

    chat.adapter.queue(text("Masih bisa."))
    chat.post(
        "/chat/messages", json={"body": "masih kebaca?", "conversation_id": thread}
    ).raise_for_status()

    bodies = [
        m["body"] for m in chat.get("/chat/messages", params={"conversation_id": thread}).json()
    ]
    assert "masih kebaca?" in bodies


def test_archiving_the_last_thread_still_leaves_somewhere_to_type(chat):
    chat.adapter.queue(text("Oke."))
    send(chat, "catat makan")
    thread = _threads(chat)[0]["id"]

    chat.patch(f"/chat/conversations/{thread}", json={"is_archived": True}).raise_for_status()

    chat.adapter.queue(text("Thread baru."))
    send(chat, "halo lagi")

    live = _threads(chat)
    assert len(live) == 1
    assert live[0]["id"] != thread


def test_cannot_touch_another_users_thread(chat):
    """AC08: zero cross-account access, threads included."""
    from fastapi.testclient import TestClient

    from app.main import app

    chat.adapter.queue(text("Oke."))
    send(chat, "catat makan")
    mine = _threads(chat)[0]["id"]

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "lain2@example.com", "password": PASSWORD}
        ).raise_for_status()

        assert (
            other.patch(f"/chat/conversations/{mine}", json={"title": "milikku"}).status_code == 404
        )
        assert other.get("/chat/messages", params={"conversation_id": mine}).status_code == 404
        assert (
            other.post("/chat/messages", json={"body": "halo", "conversation_id": mine}).status_code
            == 404
        )


def test_cannot_quote_a_message_from_another_thread(chat):
    """A quote lifted across threads arrives with no context behind it,
    and the model would be answering about a turn it cannot see."""
    chat.adapter.queue(text("Jawaban di thread lama."))
    send(chat, "pertanyaan lama")
    old = next(m for m in chat.get("/chat/messages").json() if m["role"] == "assistant")

    second = chat.post("/chat/conversations").json()

    response = chat.post(
        "/chat/messages",
        json={"body": "itu gimana?", "conversation_id": second["id"], "reply_to_id": old["id"]},
    )
    assert response.status_code == 404


# ----------------------------------------------------------------------
# Several entries from one sentence.


def _wallets(chat):
    make_account(chat, "Tunai", "cash", balance=486_000, alias="cash")
    make_account(chat, "GoPay", "ewallet", balance=184_000, alias="gopay")
    make_account(chat, "BCA", balance=2_255_000, alias="bca")


def _batch(chat, items, stated_total=None, body="tadi pagi belanja"):
    args = {"transactions": items}

    if stated_total is not None:
        args["stated_total"] = stated_total

    chat.adapter.queue(tool("propose_transactions", args))
    chat.adapter.queue(text("Ini draftnya."))

    return send(chat, body)["drafts"]


def test_one_sentence_of_three_entries_makes_one_card(chat):
    """One thing said, one thing to confirm. Three cards would be three
    swipes for one sentence, and a half-posted batch if one failed."""
    _wallets(chat)

    drafts = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "cash", "category": "obat"},
            {"type": "expense", "amount": 70_000, "from_account": "cash", "category": "makan"},
            {"type": "expense", "amount": 30_000, "from_account": "cash", "category": "minum"},
        ],
        stated_total=150_000,
    )

    assert len(drafts) == 1
    assert drafts[0]["kind"] == "batch"
    assert len(drafts[0]["payload"]["items"]) == 3


def test_the_spoken_total_is_not_recorded_as_a_fourth_entry(chat):
    """The whole point: 50 + 70 + 30 with 150rb said out loud has to
    take 150.000 out of the wallet, not 300.000."""
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "cash"},
            {"type": "expense", "amount": 70_000, "from_account": "cash"},
            {"type": "expense", "amount": 30_000, "from_account": "cash"},
        ],
        stated_total=150_000,
    )[0]

    assert draft["payload"]["matches"] is True
    assert draft["payload"]["items_total"] == 150_000

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    assert balances(chat)["Tunai"] == 336_000


def test_the_card_shows_one_before_and_after_per_wallet(chat):
    """Two expenses from one wallet are one movement of that balance,
    not two overlapping previews of the same number."""
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "cash"},
            {"type": "expense", "amount": 70_000, "from_account": "cash"},
        ],
    )[0]

    cash = [row for row in draft["impact"] if row["account"] == "Tunai"]

    assert len(cash) == 1
    assert cash[0]["before"] == 486_000
    assert cash[0]["after"] == 366_000


def test_a_mismatch_is_surfaced_and_only_the_parts_are_posted(chat):
    """Said 200, itemised 150. The backend reports the gap and refuses
    to invent an entry for it."""
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "cash"},
            {"type": "expense", "amount": 70_000, "from_account": "cash"},
            {"type": "expense", "amount": 30_000, "from_account": "cash"},
        ],
        stated_total=200_000,
    )[0]

    assert draft["payload"]["matches"] is False
    assert draft["payload"]["difference"] == 50_000

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    assert balances(chat)["Tunai"] == 336_000


def test_entries_confirmed_together_share_a_group(chat):
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "gopay"},
            {"type": "expense", "amount": 30_000, "from_account": "bca"},
        ],
    )[0]

    body = chat.post(f"/chat/drafts/{draft['id']}/confirm").json()

    assert len(body["transaction_ids"]) == 2
    assert body["group_id"]


def test_confirming_a_batch_twice_posts_it_once(chat):
    """AC13. Each entry carries its own key derived from the operation
    id - one shared key would make the second entry look like a replay
    of the first and drop it."""
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "cash"},
            {"type": "expense", "amount": 70_000, "from_account": "cash"},
        ],
    )[0]

    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 200
    assert chat.post(f"/chat/drafts/{draft['id']}/confirm").status_code == 404

    assert balances(chat)["Tunai"] == 366_000


def test_an_unclear_wallet_leaves_the_entry_blank_instead_of_failing(chat):
    """A wallet named next to one item does not cover the one before
    it. Erroring would throw away the two the model read correctly."""
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "gopay"},
            {"type": "expense", "amount": 70_000},
            {"type": "expense", "amount": 30_000, "from_account": "bca"},
        ],
        stated_total=150_000,
    )[0]

    items = draft["payload"]["items"]

    assert items[0]["unresolved"] == []
    assert items[1]["unresolved"] == ["from_account_id"]
    assert items[2]["unresolved"] == []


def test_a_batch_with_an_unchosen_wallet_cannot_be_confirmed(chat):
    """AC04 enforced on the server, not only by a disabled button."""
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "gopay"},
            {"type": "expense", "amount": 70_000},
        ],
    )[0]

    response = chat.post(f"/chat/drafts/{draft['id']}/confirm")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "batch_incomplete"
    assert balances(chat)["GoPay"] == 184_000


def test_choosing_the_missing_wallet_unlocks_the_batch(chat):
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "gopay"},
            {"type": "expense", "amount": 70_000},
        ],
    )[0]

    bca = next(a for a in chat.get("/accounts").json() if a["name"] == "BCA")

    revised = chat.post(
        f"/chat/drafts/{draft['id']}/revise",
        json={"patch": {"item": 1, "from_account_id": bca["id"]}},
    )
    assert revised.status_code == 200, revised.text

    body = revised.json()
    assert body["payload"]["items"][1]["unresolved"] == []

    chat.post(f"/chat/drafts/{body['id']}/confirm").raise_for_status()

    money = balances(chat)
    assert money["GoPay"] == 134_000
    assert money["BCA"] == 2_185_000


def test_an_unresolved_entry_is_left_out_of_the_preview(chat):
    """An impact row for a wallet nobody has chosen would be a figure
    the backend made up."""
    _wallets(chat)

    draft = _batch(
        chat,
        [
            {"type": "expense", "amount": 50_000, "from_account": "gopay"},
            {"type": "expense", "amount": 70_000},
        ],
    )[0]

    assert [row["account"] for row in draft["impact"] if row["account"] == "BCA"] == []

    gopay = next(row for row in draft["impact"] if row["account"] == "GoPay")
    assert gopay["after"] == 134_000


def test_a_single_entry_is_still_a_plain_card(chat):
    """Nothing changes for the ordinary one-line case."""
    _wallets(chat)

    drafts = _batch(chat, [{"type": "expense", "amount": 35_000, "from_account": "bca"}])

    assert len(drafts) == 1
    assert drafts[0]["kind"] == "expense"


# ----------------------------------------------------------------------
# A breakdown the client can draw, rather than only read out.


def test_a_spending_question_attaches_a_card_to_the_answer(chat):
    """Prose is a bad way to deliver a breakdown. The card is built
    from the tool's own output, so the picture and the sentence cannot
    disagree about the numbers."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": 35_000,
                        "from_account": "bca",
                        "category": "Makan",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "makan 35rb pakai bca")["drafts"][0]
    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    chat.adapter.queue(tool("get_spending", {"period": "bulan_ini"}))
    chat.adapter.queue(text("Bulan ini kamu keluar Rp35.000."))
    send(chat, "pengeluaran bulan ini berapa?")

    answer = [m for m in chat.get("/chat/messages").json() if m["role"] == "assistant"][-1]

    assert answer["view"]["kind"] == "spending"
    assert answer["view"]["data"]["expense_total"] == 35_000
    assert [c["name"] for c in answer["view"]["data"]["categories"]] == ["Makan"]


def test_an_ordinary_answer_carries_no_card(chat):
    chat.adapter.queue(text("Halo!"))
    send(chat, "halo")

    answer = [m for m in chat.get("/chat/messages").json() if m["role"] == "assistant"][-1]

    assert answer["view"] is None


def test_the_breakdown_comes_with_the_window_before_it(chat):
    """A total answers "what did I spend". The comparison answers the
    question people actually ask, which is whether that is a lot."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(tool("get_spending", {"period": "bulan_ini"}))
    chat.adapter.queue(text("Belum ada pengeluaran."))
    send(chat, "pengeluaran bulan ini?")

    data = [m for m in chat.get("/chat/messages").json() if m["role"] == "assistant"][-1]["view"][
        "data"
    ]

    assert "previous_expense_total" in data
    assert isinstance(data["previous_expense_total"], int)


def test_a_category_over_its_budget_says_by_how_much(chat):
    """Colour alone cannot carry it (FR18), so the figure travels with
    the row and the card has something to put in words."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")
    chat.put("/budgets", json={"category": "Makan", "amount": 20_000}).raise_for_status()

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": 35_000,
                        "from_account": "bca",
                        "category": "Makan",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "makan 35rb pakai bca")["drafts"][0]
    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    chat.adapter.queue(tool("get_spending", {"period": "bulan_ini"}))
    chat.adapter.queue(text("Makan lewat budget."))
    send(chat, "pengeluaran bulan ini?")

    data = [m for m in chat.get("/chat/messages").json() if m["role"] == "assistant"][-1]["view"][
        "data"
    ]
    makan = next(c for c in data["categories"] if c["name"] == "Makan")

    assert makan["limit"] == 20_000
    assert makan["over"] == 15_000


def test_a_category_with_no_budget_is_not_called_within_one(chat):
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": 35_000,
                        "from_account": "bca",
                        "category": "Kopi",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))
    draft = send(chat, "kopi 35rb pakai bca")["drafts"][0]
    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    chat.adapter.queue(tool("get_spending", {"period": "bulan_ini"}))
    chat.adapter.queue(text("Kopi 35rb."))
    send(chat, "pengeluaran bulan ini?")

    data = [m for m in chat.get("/chat/messages").json() if m["role"] == "assistant"][-1]["view"][
        "data"
    ]
    kopi = next(c for c in data["categories"] if c["name"] == "Kopi")

    assert kopi["limit"] is None
    assert kopi["over"] is None


# ----------------------------------------------------------------------
# The model narrating a draft instead of raising one.


def test_a_reply_that_asks_the_user_to_confirm_is_retried(chat):
    """Observed against the real model: it lists the entries, asks
    "apakah ini sudah benar?" and waits. There is no card, so "ok"
    does nothing and the person is stuck repeating themselves."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(
        text(
            "Baik, saya akan catat transaksi tadi pagi Anda:\n"
            "1. **Obat**: Rp 50.000 dari **gopay**\n\n"
            "Apakah ini sudah benar? Jika ada yang perlu disesuaikan, beri tahu saya."
        )
    )
    # The nudge round: this time it calls the tool.
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 50_000, "from_account": "bca"}]},
        )
    )

    result = send(chat, "tadi pagi beli obat 50rb")

    assert len(result["drafts"]) == 1
    assert result["drafts"][0]["payload"]["amount"] == 50_000


def test_akan_catat_counts_as_claiming_a_draft(chat):
    """The guard used to require "saya catat" as adjacent words, so
    every phrasing with "akan" between them went through untouched."""
    make_account(chat, "BCA", balance=1_000_000, alias="bca")

    chat.adapter.queue(text("Oke, saya akan catat pengeluaran itu ya."))
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "bca"}]},
        )
    )

    assert len(send(chat, "makan 35rb pakai bca")["drafts"]) == 1


def test_an_ordinary_answer_is_not_retried(chat):
    """A false positive would push the model to invent a draft nobody
    asked for, so the guard has to leave plain answers alone."""
    chat.adapter.queue(text("Saldo BCA kamu Rp2.255.000, naik dari minggu lalu."))

    result = send(chat, "saldo bca berapa?")

    assert result["drafts"] == []
    assert result["reply"].startswith("Saldo BCA")
    # One round only: a retry would have consumed a second script entry.
    assert len(chat.adapter.calls) == 1


def test_asking_which_wallet_is_not_retried(chat):
    """Asking about an ambiguous wallet is correct behaviour (AC04).
    Nudging it would turn a good question into a guess."""
    chat.adapter.queue(text("Kantong mana yang kamu maksud, BCA Utama atau BCA Gaji?"))

    result = send(chat, "makan 35rb pakai bca")

    assert result["drafts"] == []
    assert len(chat.adapter.calls) == 1


def test_a_refused_tool_says_why_instead_of_generic_advice(chat):
    """The retry's fallback used to tell people to "sebutkan nominal dan
    kantongnya" even when the real problem was that two of their wallets
    are called BCA - advice about a problem they did not have."""
    make_account(chat, "BCA Utama", balance=1_000_000, alias="utama")
    make_account(chat, "BCA Gaji", balance=1_000_000, alias="gaji")

    chat.adapter.queue(text("Saya akan catat pengeluaran itu."))
    chat.adapter.queue(
        tool(
            "propose_transactions",
            {"transactions": [{"type": "expense", "amount": 35_000, "from_account": "BCA"}]},
        )
    )

    result = send(chat, "makan 35rb pakai bca")

    assert result["drafts"] == []
    assert "BCA" in result["reply"]
    assert "35rb pakai BCA" not in result["reply"]


# ----------------------------------------------------------------------
# Sending money to a person is not moving it between your own wallets.


def test_a_transfer_to_a_person_says_what_to_do_instead(chat):
    """Reported from real use: "gua abis tf ke ibu gua 300rb dari bank
    jago" answered "Tidak ada kantong yang cocok dengan 'Ibu'", and the
    model repeated the same call even after being told it was an
    expense. The error was a dead end; now it names the right call."""
    make_account(chat, "Bank Jago", balance=1_000_000, alias="jago")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "transfer",
                        "amount": 300_000,
                        "from_account": "jago",
                        "to_account": "Ibu",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Oke, aku catat sebagai pengeluaran."))

    send(chat, "gua abis tf ke ibu gua 300rb dari bank jago")

    # The tool result the model was handed has to carry the way out.
    tool_messages = [m for m in chat.adapter.calls[-1]["messages"] if m.get("role") == "tool"]
    said = tool_messages[-1]["content"]

    assert "expense" in said
    assert "merchant" in said
    assert "Ibu" in said


def test_the_hint_is_only_for_the_destination(chat):
    """A source wallet that does not resolve is a different mistake:
    the money came from somewhere the person owns either way."""
    make_account(chat, "Bank Jago", balance=1_000_000, alias="jago")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "transfer",
                        "amount": 300_000,
                        "from_account": "Dompet Ajaib",
                        "to_account": "jago",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Kantong mana?"))

    send(chat, "pindahin 300rb dari dompet ajaib ke jago")

    tool_messages = [m for m in chat.adapter.calls[-1]["messages"] if m.get("role") == "tool"]
    said = tool_messages[-1]["content"]

    assert "Dompet Ajaib" in said
    assert "merchant" not in said


def test_an_expense_to_a_person_still_works(chat):
    """The shape the model should reach for: money out, person named."""
    make_account(chat, "Bank Jago", balance=1_000_000, alias="jago")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": 300_000,
                        "from_account": "jago",
                        "merchant": "Ibu",
                        "category": "Keluarga",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))

    draft = send(chat, "gua abis tf ke ibu gua 300rb dari bank jago")["drafts"][0]

    assert draft["kind"] == "expense"
    assert draft["payload"]["merchant"] == "Ibu"

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    # Money left, so it is an expense and the balance drops.
    assert balances(chat)["Bank Jago"] == 700_000


def test_a_real_wallet_transfer_is_still_a_transfer(chat):
    """The rule it must not break: moving money between the person's
    own wallets is neither income nor expense (AC02)."""
    make_account(chat, "Bank Jago", balance=1_000_000, alias="jago")
    make_account(chat, "GoPay", "ewallet", balance=0, alias="gopay")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "transfer",
                        "amount": 300_000,
                        "from_account": "jago",
                        "to_account": "gopay",
                    }
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))

    draft = send(chat, "top up gopay 300rb dari jago")["drafts"][0]
    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    money = balances(chat)
    assert money["Bank Jago"] == 700_000
    assert money["GoPay"] == 300_000


# ----------------------------------------------------------------------
# What the money was for, kept with the money.


def _spend(chat, item, body="catat ini"):
    chat.adapter.queue(tool("propose_transactions", {"transactions": [item]}))
    chat.adapter.queue(text("Ini draftnya."))

    return send(chat, body)["drafts"][0]


def test_the_note_survives_to_the_stored_transaction(chat):
    """The three keepsakes are separate on purpose: what kind, to whom,
    and what for. All three have to reach the ledger, or the card is
    describing something the record does not hold."""
    make_account(chat, "Bank Jago", balance=1_000_000, alias="jago")

    draft = _spend(
        chat,
        {
            "type": "expense",
            "amount": 300_000,
            "from_account": "jago",
            "merchant": "Ibu",
            "category": "Keluarga",
            "note": "tf ke ibu buat top up saldo pulsa",
        },
        body="abis tf 300rb ke ibu buat topup saldo pulsa, pake bank jago",
    )

    assert draft["payload"]["note"] == "tf ke ibu buat top up saldo pulsa"
    assert draft["payload"]["merchant"] == "Ibu"
    assert draft["payload"]["category"] == "Keluarga"

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    row = next(t for t in chat.get("/transactions").json() if t["merchant"] == "Ibu")
    assert row["note"] == "tf ke ibu buat top up saldo pulsa"


def test_a_note_in_a_batch_reaches_the_ledger_too(chat):
    """Entries from one sentence each keep their own reason."""
    make_account(chat, "Bank Jago", balance=1_000_000, alias="jago")

    chat.adapter.queue(
        tool(
            "propose_transactions",
            {
                "transactions": [
                    {
                        "type": "expense",
                        "amount": 25_000,
                        "from_account": "jago",
                        "merchant": "APTB",
                        "category": "Transport",
                        "note": "ongkos bus APTB berangkat kerja",
                    },
                    {
                        "type": "expense",
                        "amount": 18_000,
                        "from_account": "jago",
                        "category": "Makan",
                        "note": "sarapan di kantin",
                    },
                ]
            },
        )
    )
    chat.adapter.queue(text("Ini draftnya."))

    draft = send(chat, "ongkos bus aptb 25rb, sarapan 18rb, dari jago")["drafts"][0]

    assert [i["note"] for i in draft["payload"]["items"]] == [
        "ongkos bus APTB berangkat kerja",
        "sarapan di kantin",
    ]

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    stored = {t["note"] for t in chat.get("/transactions").json()}
    assert "ongkos bus APTB berangkat kerja" in stored
    assert "sarapan di kantin" in stored


def test_a_transaction_without_a_reason_keeps_no_note(chat):
    """An empty note is better than an invented one: nothing in the
    message said what it was for."""
    make_account(chat, "Bank Jago", balance=1_000_000, alias="jago")

    draft = _spend(
        chat,
        {"type": "expense", "amount": 50_000, "from_account": "jago"},
        body="keluar 50rb dari jago",
    )

    assert draft["payload"].get("note") is None

    chat.post(f"/chat/drafts/{draft['id']}/confirm").raise_for_status()

    # The opening balance is the only other row, and it carries no note
    # either; what matters is that none was invented for this one.
    assert all(t["note"] is None for t in chat.get("/transactions").json())


def test_the_model_is_told_what_each_field_is_for(chat):
    """These three arrived as bare `{"type": "string"}` with no
    description at all, which is why they came back empty: the model
    was never told they existed for anything."""
    from app.services.chat.tools import ALL_TOOLS

    schema = next(t for t in ALL_TOOLS if t["function"]["name"] == "propose_transactions")
    fields = schema["function"]["parameters"]["properties"]["transactions"]["items"]["properties"]

    for name in ("note", "merchant", "category"):
        assert fields[name].get("description"), f"{name} has no description"

    assert "merchant" in fields["note"]["description"] or "nominal" in fields["note"]["description"]
