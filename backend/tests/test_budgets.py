"""Budgets (PRD FR08).

The pure evaluation first, then the behaviour the PRD warns about: a
budget is a plan, not money, so it must never reduce what the user has
available to spend.
"""

from __future__ import annotations

import pytest

from app.domain.budgets import BudgetState, evaluate, summarise
from app.money import MoneyError

from .conftest import requires_db

PASSWORD = "sangat-rahasia-123"


# ----------------------------------------------------------------------
# Evaluation
# ----------------------------------------------------------------------


def test_well_within_budget():
    status = evaluate(category="Makan", limit=1_000_000, spent=200_000)

    assert status.state is BudgetState.OK
    assert status.remaining == 800_000
    assert status.percent == 20
    assert status.overspend == 0


def test_approaching_the_limit_is_flagged_before_it_is_breached():
    status = evaluate(category="Makan", limit=1_000_000, spent=800_000)

    assert status.state is BudgetState.APPROACHING
    assert status.remaining == 200_000


def test_spending_exactly_the_limit_is_not_yet_exceeded():
    status = evaluate(category="Makan", limit=1_000_000, spent=1_000_000)

    assert status.state is BudgetState.APPROACHING
    assert status.remaining == 0
    assert status.percent == 100


def test_overspending_is_reported_with_its_real_size():
    status = evaluate(category="Makan", limit=1_000_000, spent=1_300_000)

    assert status.state is BudgetState.EXCEEDED
    # Negative, not clamped: hiding the overspend defeats the point.
    assert status.remaining == -300_000
    assert status.overspend == 300_000
    assert status.percent == 130, "uncapped, so 30% over is visible"


def test_net_negative_spending_after_refunds_is_reported_as_is():
    """Refunds can exceed purchases in a period. Say so, do not floor it."""
    status = evaluate(category="Belanja", limit=1_000_000, spent=-50_000)

    assert status.state is BudgetState.OK
    assert status.remaining == 1_050_000


@pytest.mark.parametrize("limit", [0, -1, 1_000_000.5])
def test_an_invalid_limit_is_rejected(limit):
    with pytest.raises(MoneyError):
        evaluate(category="Makan", limit=limit, spent=0)


def test_summary_keeps_breaches_visible_even_when_totals_net_out():
    statuses = [
        evaluate(category="Makan", limit=1_000_000, spent=1_500_000),
        evaluate(category="Transport", limit=1_000_000, spent=200_000),
    ]

    summary = summarise(statuses)

    assert summary.total_limit == 2_000_000
    assert summary.total_spent == 1_700_000
    # Overall still within budget...
    assert summary.total_remaining == 300_000
    # ...but the breach is not hidden by that.
    assert summary.exceeded == ["Makan"]


# ----------------------------------------------------------------------
# Over HTTP
# ----------------------------------------------------------------------

pytestmark_integration = [requires_db, pytest.mark.integration]


@pytest.fixture
def api(engine, monkeypatch, reset_tables):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "budget@example.com", "password": PASSWORD}
        ).raise_for_status()
        yield client

    reset_tables(factory)


def account(api, name="BCA", balance=5_000_000, type_="bank"):
    r = api.post("/accounts", json={"name": name, "type": type_, "opening_balance": balance})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def spend(api, account_id, amount, category):
    import uuid

    r = api.post(
        "/transactions",
        headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        json={
            "type": "expense",
            "amount": amount,
            "from_account_id": account_id,
            "category": category,
        },
    )
    assert r.status_code == 201, r.text


def budgets(api, period="bulan_ini"):
    r = api.get("/budgets", params={"period": period})
    assert r.status_code == 200, r.text
    return r.json()


@requires_db
@pytest.mark.integration
def test_a_budget_does_not_reduce_free_to_spend(api):
    """The PRD's explicit warning: a budget is a plan, not a claim on cash."""
    account(api, balance=5_000_000)

    before = api.get("/summary").json()

    api.put("/budgets", json={"category": "Makan", "amount": 2_000_000}).raise_for_status()

    after = api.get("/summary").json()

    assert after["free_to_spend"] == before["free_to_spend"] == 5_000_000
    assert after["liquid"] == before["liquid"]
    assert after["allocated"] == 0, "a budget is not an allocation"


@requires_db
@pytest.mark.integration
def test_spending_counts_against_its_category(api):
    account_id = account(api)
    api.put("/budgets", json={"category": "Makan", "amount": 1_000_000}).raise_for_status()

    spend(api, account_id, 300_000, "Makan")
    spend(api, account_id, 50_000, "Transport")

    report = budgets(api)
    makan = next(b for b in report["budgets"] if b["category"] == "Makan")

    assert makan["spent"] == 300_000
    assert makan["remaining"] == 700_000
    assert len(report["budgets"]) == 1, "only budgeted categories are listed"


@requires_db
@pytest.mark.integration
def test_a_transfer_does_not_consume_a_budget(api):
    """AC02 again: moving your own money is not spending."""
    bca = account(api, "BCA", balance=5_000_000)
    gopay = account(api, "GoPay", balance=0, type_="ewallet")
    api.put("/budgets", json={"category": "Makan", "amount": 1_000_000}).raise_for_status()

    import uuid

    api.post(
        "/transactions",
        headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        json={
            "type": "transfer",
            "amount": 500_000,
            "from_account_id": bca,
            "to_account_id": gopay,
        },
    ).raise_for_status()

    assert budgets(api)["budgets"][0]["spent"] == 0


@requires_db
@pytest.mark.integration
def test_paying_a_card_bill_does_not_consume_a_budget(api):
    """AC03: the spending was counted at purchase; the payment is not new."""
    import uuid

    bca = account(api, "BCA", balance=5_000_000)
    card = account(api, "Kartu", balance=0, type_="credit_card")
    api.put("/budgets", json={"category": "Belanja", "amount": 1_000_000}).raise_for_status()

    spend(api, card, 800_000, "Belanja")
    api.post(
        "/transactions",
        headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        json={
            "type": "card_payment",
            "amount": 800_000,
            "from_account_id": bca,
            "card_account_id": card,
        },
    ).raise_for_status()

    status = budgets(api)["budgets"][0]

    assert status["spent"] == 800_000, "counted once, when it was bought"


@requires_db
@pytest.mark.integration
def test_a_refund_frees_budget_back_up(api):
    import uuid

    account_id = account(api)
    api.put("/budgets", json={"category": "Belanja", "amount": 1_000_000}).raise_for_status()

    spend(api, account_id, 400_000, "Belanja")
    api.post(
        "/transactions",
        headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        json={
            "type": "refund",
            "amount": 150_000,
            "to_account_id": account_id,
            "category": "Belanja",
        },
    ).raise_for_status()

    status = budgets(api)["budgets"][0]

    assert status["spent"] == 250_000
    assert status["remaining"] == 750_000


@requires_db
@pytest.mark.integration
def test_the_state_moves_from_ok_to_approaching_to_exceeded(api):
    account_id = account(api, balance=10_000_000)
    api.put("/budgets", json={"category": "Makan", "amount": 1_000_000}).raise_for_status()

    spend(api, account_id, 500_000, "Makan")
    assert budgets(api)["budgets"][0]["state"] == "ok"

    spend(api, account_id, 350_000, "Makan")
    assert budgets(api)["budgets"][0]["state"] == "approaching"

    spend(api, account_id, 300_000, "Makan")
    report = budgets(api)
    assert report["budgets"][0]["state"] == "exceeded"
    assert report["exceeded"] == ["Makan"]
    assert report["budgets"][0]["remaining"] == -150_000


@requires_db
@pytest.mark.integration
def test_setting_a_budget_twice_replaces_rather_than_adds(api):
    api.put("/budgets", json={"category": "Makan", "amount": 1_000_000}).raise_for_status()
    api.put("/budgets", json={"category": "Makan", "amount": 1_500_000}).raise_for_status()

    report = budgets(api)

    assert len(report["budgets"]) == 1
    assert report["budgets"][0]["limit"] == 1_500_000


@requires_db
@pytest.mark.integration
def test_a_budget_can_be_set_before_the_category_is_ever_used(api):
    """ "Keep transport under 500k" comes before the first trip."""
    api.put("/budgets", json={"category": "Transport", "amount": 500_000}).raise_for_status()

    status = budgets(api)["budgets"][0]

    assert status["category"] == "Transport"
    assert status["spent"] == 0


@requires_db
@pytest.mark.integration
def test_budgets_are_scoped_to_the_period(api):
    account_id = account(api)
    api.put("/budgets", json={"category": "Makan", "amount": 1_000_000}).raise_for_status()
    spend(api, account_id, 300_000, "Makan")

    assert budgets(api, "bulan_ini")["budgets"][0]["spent"] == 300_000
    assert budgets(api, "bulan_lalu")["budgets"][0]["spent"] == 0


@requires_db
@pytest.mark.integration
def test_removing_a_budget(api):
    api.put("/budgets", json={"category": "Makan", "amount": 1_000_000}).raise_for_status()

    assert api.delete("/budgets", params={"category": "Makan"}).status_code == 204
    assert budgets(api)["budgets"] == []
    assert api.delete("/budgets", params={"category": "Makan"}).status_code == 404


@requires_db
@pytest.mark.integration
def test_budgets_require_a_session(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        assert anon.get("/budgets").status_code == 401
        assert anon.put("/budgets", json={"category": "x", "amount": 1}).status_code == 401


@requires_db
@pytest.mark.integration
def test_budgets_are_scoped_to_the_owner(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    api.put("/budgets", json={"category": "Makan", "amount": 1_000_000}).raise_for_status()

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "nosy4@example.com", "password": PASSWORD}
        ).raise_for_status()
        assert other.get("/budgets").json()["budgets"] == []
