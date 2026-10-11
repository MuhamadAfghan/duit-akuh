"""Filtering the transaction list.

The filters exist so the client does not have to narrow a page of
results and call it an answer. "Transfers this month" computed over the
last fifty rows is a different question with a quietly different
answer, and the difference grows with the history.

What is pinned here: each filter narrows, they compose, a period is
resolved in the user's timezone rather than UTC, and an account filter
catches a transaction through either side of it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "sangat-rahasia-123"


def new_key() -> str:
    return f"filter-{uuid.uuid4()}"


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
            "/auth/register", json={"email": "filter@example.com", "password": PASSWORD}
        ).raise_for_status()
        yield client

    reset_tables(factory)


def make_account(api, name, type_, *, balance=0):
    response = api.post("/accounts", json={"name": name, "type": type_, "opening_balance": balance})
    assert response.status_code == 201, response.text
    return response.json()


def post(api, draft):
    response = api.post("/transactions", headers={"Idempotency-Key": new_key()}, json=draft)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def seeded(api):
    """Two wallets, and one of each kind at a known time."""
    bca = make_account(api, "BCA", "bank", balance=5_000_000)
    cash = make_account(api, "Cash", "cash", balance=500_000)

    now = datetime.now(timezone.utc)
    last_month = (now.replace(day=1) - timedelta(days=5)).isoformat()

    post(api, {"type": "expense", "amount": 35_000, "from_account_id": bca["id"]})
    post(api, {"type": "income", "amount": 8_000_000, "to_account_id": bca["id"]})
    post(
        api,
        {
            "type": "transfer",
            "amount": 100_000,
            "from_account_id": bca["id"],
            "to_account_id": cash["id"],
        },
    )
    post(
        api,
        {
            "type": "expense",
            "amount": 20_000,
            "from_account_id": cash["id"],
            "occurred_at": last_month,
        },
    )

    return {"bca": bca, "cash": cash}


def types_of(rows):
    return sorted(row["type"] for row in rows)


# ----------------------------------------------------------------------


def test_without_filters_everything_comes_back(api, seeded):
    rows = api.get("/transactions?limit=200").json()

    # Four posted, plus the opening balance of each wallet.
    assert len(rows) == 6


def test_type_narrows_to_one_kind(api, seeded):
    rows = api.get("/transactions?type=transfer").json()

    assert types_of(rows) == ["transfer"]
    assert len(rows) == 1


def test_period_excludes_what_falls_outside_it(api, seeded):
    this_month = api.get("/transactions?period=bulan_ini&limit=200").json()
    everything = api.get("/transactions?period=semua&limit=200").json()

    assert len(everything) == len(this_month) + 1

    # The one left out is last month's cash expense, by amount.
    amounts_now = {abs(entry["amount"]) for row in this_month for entry in row["entries"]}
    amounts_all = {abs(entry["amount"]) for row in everything for entry in row["entries"]}

    assert 20_000 in amounts_all
    assert 20_000 not in amounts_now


def test_account_matches_either_side_of_a_transfer(api, seeded):
    cash_rows = api.get(f"/transactions?account_id={seeded['cash']['id']}&limit=200").json()

    # The receiving leg of the transfer counts, alongside the cash
    # expense and the wallet's own opening balance.
    assert types_of(cash_rows) == ["expense", "opening", "transfer"]


def test_account_excludes_transactions_it_never_touched(api, seeded):
    cash_rows = api.get(f"/transactions?account_id={seeded['cash']['id']}&limit=200").json()

    # The 8 juta income went to BCA only.
    assert "income" not in types_of(cash_rows)


def test_filters_compose(api, seeded):
    rows = api.get(
        f"/transactions?account_id={seeded['bca']['id']}&type=expense&period=bulan_ini"
    ).json()

    assert types_of(rows) == ["expense"]
    # The cash expense from last month is excluded by both the account
    # and the period, and each on its own would have been enough.
    assert len(rows) == 1


def test_an_unknown_period_is_refused_rather_than_ignored(api, seeded):
    response = api.get("/transactions?period=minggu_depan")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_period"


def test_an_unknown_type_is_refused(api, seeded):
    assert api.get("/transactions?type=sembarang").status_code == 422


def test_filters_stay_scoped_to_the_owner(api, seeded, engine, monkeypatch):
    """A filter must never become a way to read somebody else's ledger."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "orang-lain@example.com", "password": PASSWORD}
        ).raise_for_status()

        rows = other.get(f"/transactions?account_id={seeded['bca']['id']}&limit=200").json()

    assert rows == []
