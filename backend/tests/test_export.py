"""CSV export (PRD section 9, AC10).

AC10 asks that the export match the filter the user applied and the
number of transactions. The other thing worth proving is that a CSV
built from user-entered text cannot execute when a spreadsheet opens
it.
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "sangat-rahasia-123"


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
            "/auth/register", json={"email": "export@example.com", "password": PASSWORD}
        ).raise_for_status()
        yield client

    reset_tables(factory)


def account(api, name="BCA", balance=5_000_000, type_="bank"):
    r = api.post("/accounts", json={"name": name, "type": type_, "opening_balance": balance})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def post(api, body):
    r = api.post("/transactions", headers={"Idempotency-Key": f"k-{uuid.uuid4()}"}, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def download(api, **params) -> list[dict]:
    response = api.get("/export/transactions.csv", params=params or {"period": "semua"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    return list(csv.DictReader(io.StringIO(response.text)))


# ----------------------------------------------------------------------


def test_an_empty_export_still_has_its_header(api):
    rows = download(api)

    assert rows == []
    response = api.get("/export/transactions.csv", params={"period": "semua"})
    assert response.text.splitlines()[0].startswith("transaction_id,")


def test_one_row_per_entry_so_both_sides_of_a_transfer_survive(api):
    """Collapsing a transfer to one row would force a choice about which
    account to show, and lose the other."""
    bca = account(api, "BCA", balance=1_000_000)
    gopay = account(api, "GoPay", balance=0, type_="ewallet")

    post(
        api,
        {
            "type": "transfer",
            "amount": 100_000,
            "from_account_id": bca,
            "to_account_id": gopay,
            "fee": 2_500,
        },
    )

    rows = [r for r in download(api) if r["type"] == "transfer"]

    assert len(rows) == 3, "source, destination, and the fee leg"
    assert {r["account"] for r in rows} == {"BCA", "GoPay", "Biaya admin"}
    # The ledger invariant survives the round trip.
    assert sum(int(r["amount"]) for r in rows) == 0
    assert len({r["transaction_id"] for r in rows}) == 1


def test_amounts_export_as_plain_integers(api):
    account_id = account(api)
    post(api, {"type": "expense", "amount": 35_000, "from_account_id": account_id})

    amounts = [r["amount"] for r in download(api)]

    for amount in amounts:
        assert int(amount) == float(amount), "no separators, no decimals"
    assert "-35000" in amounts


def test_ac10_the_export_honours_the_filter(api):
    from datetime import datetime, timezone

    account_id = account(api)

    post(
        api,
        {
            "type": "expense",
            "amount": 10_000,
            "from_account_id": account_id,
            "occurred_at": datetime(2026, 9, 15, 5, tzinfo=timezone.utc).isoformat(),
        },
    )
    post(
        api,
        {
            "type": "expense",
            "amount": 20_000,
            "from_account_id": account_id,
            "occurred_at": datetime(2026, 10, 3, 5, tzinfo=timezone.utc).isoformat(),
        },
    )

    september = download(api, start="2026-09-01", end="2026-09-30")
    october = download(api, start="2026-10-01", end="2026-10-31")

    assert {abs(int(r["amount"])) for r in september} == {10_000}

    # The account's opening balance is dated today, so it is a genuine
    # October row and belongs in that export alongside the expense.
    assert {abs(int(r["amount"])) for r in october} == {20_000, 5_000_000}
    assert {r["type"] for r in october} == {"expense", "opening"}


def test_the_export_counts_match_the_transactions(api):
    """AC10: the export must agree with what the app says it holds."""
    account_id = account(api)

    for _ in range(5):
        post(api, {"type": "expense", "amount": 1_000, "from_account_id": account_id})

    rows = download(api)
    transactions = api.get("/transactions").json()

    assert len({r["transaction_id"] for r in rows}) == len(transactions)


def test_a_reversal_and_its_original_both_appear(api):
    """Nothing is deleted, so nothing may be missing from the export."""
    account_id = account(api)
    posted = post(api, {"type": "expense", "amount": 35_000, "from_account_id": account_id})

    api.post(
        f"/transactions/{posted['id']}/reverse", headers={"Idempotency-Key": f"r-{uuid.uuid4()}"}
    ).raise_for_status()

    rows = download(api)
    types = {r["type"] for r in rows}

    assert "expense" in types
    assert "reversal" in types
    assert any(r["status"] == "reversed" for r in rows)


# ----------------------------------------------------------------------
# Spreadsheet formula injection
# ----------------------------------------------------------------------


@pytest.mark.parametrize("payload", ["=1+1", "+1", "-1+1", "@SUM(A1)"])
def test_text_that_a_spreadsheet_would_execute_is_neutralised(api, payload):
    """Excel and Sheets run a cell starting with = + - or @ on open.

    The note is the user's own text here, but notes also arrive from
    chat and, later, receipt OCR.
    """
    account_id = account(api)
    post(
        api,
        {
            "type": "expense",
            "amount": 1_000,
            "from_account_id": account_id,
            "note": payload,
        },
    )

    notes = [r["note"] for r in download(api) if r["note"]]

    assert payload not in notes
    assert f"'{payload}" in notes


def test_ordinary_text_is_left_alone(api):
    account_id = account(api)
    post(
        api,
        {
            "type": "expense",
            "amount": 1_000,
            "from_account_id": account_id,
            "merchant": "Warung Bu Tini",
        },
    )

    assert "Warung Bu Tini" in [r["merchant"] for r in download(api)]


# ----------------------------------------------------------------------
# Access
# ----------------------------------------------------------------------


def test_export_requires_a_session(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        assert anon.get("/export/transactions.csv").status_code == 401


def test_the_export_contains_only_the_callers_data(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    account_id = account(api)
    post(api, {"type": "expense", "amount": 77_000, "from_account_id": account_id})

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "nosy5@example.com", "password": PASSWORD}
        ).raise_for_status()
        response = other.get("/export/transactions.csv", params={"period": "semua"})

    assert list(csv.DictReader(io.StringIO(response.text))) == []


def test_the_filename_describes_the_period(api):
    """An unbounded range must not leak its sentinel dates into the name."""
    from datetime import datetime, timezone

    from app.domain.periods import MONTH_NAMES

    now = datetime.now(timezone.utc).astimezone()
    # Derived, not hardcoded: a literal month name would start failing
    # on the first of next month.
    this_month = f"{MONTH_NAMES[now.month - 1]}-{now.year}".lower()

    cases = {
        "semua": "transaksi-sejak-awal.csv",
        "bulan_ini": f"transaksi-{this_month}.csv",
        "hari_ini": "transaksi-hari-ini.csv",
    }

    for period, expected in cases.items():
        response = api.get("/export/transactions.csv", params={"period": period})
        assert expected in response.headers["content-disposition"], period
