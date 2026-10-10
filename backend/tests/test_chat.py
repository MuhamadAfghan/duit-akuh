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

from app.services.ai.fake import FakeAdapter, outage, text, tool

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "sangat-rahasia-123"


@pytest.fixture
def chat(engine, monkeypatch):
    """TestClient with a registered user and a scripted adapter attached."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.api import routes_chat
    from app.main import app
    from app.models import (
        Account,
        AiRequestLog,
        Allocation,
        AuditEvent,
        Conversation,
        Draft,
        Entry,
        Goal,
        LoginAttempt,
        Message,
        Session,
        Transaction,
        User,
    )

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    adapter = FakeAdapter()
    routes_chat.set_adapter(adapter)

    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "chat@example.com", "password": PASSWORD}
        ).raise_for_status()
        client.adapter = adapter
        yield client

    routes_chat.set_adapter(None)

    with factory() as cleanup:
        for model in (
            AiRequestLog,
            Message,
            Conversation,
            AuditEvent,
            Entry,
            Draft,
            Transaction,
            Allocation,
            Goal,
            Account,
            Session,
            LoginAttempt,
            User,
        ):
            cleanup.query(model).delete()
        cleanup.commit()


def make_account(chat, name, type_="bank", *, balance=0, alias=None):
    body = {"name": name, "type": type_, "opening_balance": balance}
    if alias:
        body["alias"] = alias
    response = chat.post("/accounts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def balances(chat) -> dict[str, int]:
    return {a["name"]: a["balance"] for a in chat.get("/accounts").json()}


def send(chat, body: str) -> dict:
    response = chat.post("/chat/messages", json={"body": body})
    assert response.status_code == 200, response.text
    return response.json()


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
