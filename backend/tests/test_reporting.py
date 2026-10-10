"""Period reports against the database (PRD FR06).

The claims worth proving are the ones a user would notice being wrong:
that a transfer is not spending, that paying a card bill is not
spending, that a refund reduces its category, and that a purchase near
midnight lands in the month the user thinks it did.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "sangat-rahasia-123"


@pytest.fixture
def api(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app
    from app.models import (
        Account,
        Allocation,
        AuditEvent,
        Entry,
        Goal,
        LoginAttempt,
        Session,
        Transaction,
        User,
    )

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "report@example.com", "password": PASSWORD}
        ).raise_for_status()
        yield client

    with factory() as cleanup:
        for model in (
            AuditEvent,
            Entry,
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


def key() -> str:
    return f"key-{uuid.uuid4()}"


def account(api, name, type_="bank", balance=0):
    r = api.post("/accounts", json={"name": name, "type": type_, "opening_balance": balance})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def post(api, body, when: datetime | None = None):
    if when is not None:
        body = {**body, "occurred_at": when.isoformat()}
    r = api.post("/transactions", headers={"Idempotency-Key": key()}, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def spending(api, period="bulan_ini", **params):
    r = api.get("/reports/spending", params={"period": period, **params})
    assert r.status_code == 200, r.text
    return r.json()


# A Jakarta user's October 2026. Stored instants are UTC, and these are
# in the past relative to the suite's clock so that relative periods
# ("bulan_ini") behave the way a reader expects.
IN_OCTOBER = datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc)
IN_SEPTEMBER = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# What counts as spending
# ----------------------------------------------------------------------


def test_a_transfer_is_not_spending(api):
    bca = account(api, "BCA", balance=1_000_000)
    gopay = account(api, "GoPay", "ewallet")

    post(
        api,
        {"type": "transfer", "amount": 100_000, "from_account_id": bca, "to_account_id": gopay},
        IN_OCTOBER,
    )

    report = spending(api, "semua")

    assert report["expense_total"] == 0
    assert report["income_total"] == 0
    assert report["categories"] == []


def test_a_transfer_fee_is_spending_but_only_the_fee(api):
    bca = account(api, "BCA", balance=1_000_000)
    gopay = account(api, "GoPay", "ewallet")

    post(
        api,
        {
            "type": "transfer",
            "amount": 100_000,
            "from_account_id": bca,
            "to_account_id": gopay,
            "fee": 2_500,
        },
        IN_OCTOBER,
    )

    report = spending(api, "semua")

    assert report["expense_total"] == 2_500
    assert [c["name"] for c in report["categories"]] == ["Biaya admin"]


def test_paying_a_card_bill_is_not_new_spending(api):
    bca = account(api, "BCA", balance=2_000_000)
    card = account(api, "Kartu", "credit_card")

    post(
        api,
        {"type": "expense", "amount": 800_000, "from_account_id": card, "category": "Belanja"},
        IN_OCTOBER,
    )
    post(
        api,
        {
            "type": "card_payment",
            "amount": 800_000,
            "from_account_id": bca,
            "card_account_id": card,
        },
        IN_OCTOBER,
    )

    report = spending(api, "semua")

    assert report["expense_total"] == 800_000, "counted once, at purchase time"


def test_a_refund_reduces_its_category(api):
    bca = account(api, "BCA", balance=1_000_000)

    post(
        api,
        {"type": "expense", "amount": 200_000, "from_account_id": bca, "category": "Belanja"},
        IN_OCTOBER,
    )
    post(
        api,
        {"type": "refund", "amount": 50_000, "to_account_id": bca, "category": "Belanja"},
        IN_OCTOBER,
    )

    report = spending(api, "semua")

    assert report["expense_total"] == 150_000
    assert report["categories"][0] == {"name": "Belanja", "amount": 150_000}


def test_a_fully_refunded_category_is_dropped_rather_than_shown_as_zero(api):
    bca = account(api, "BCA", balance=1_000_000)

    post(
        api,
        {"type": "expense", "amount": 50_000, "from_account_id": bca, "category": "Belanja"},
        IN_OCTOBER,
    )
    post(
        api,
        {"type": "refund", "amount": 50_000, "to_account_id": bca, "category": "Belanja"},
        IN_OCTOBER,
    )

    assert spending(api, "semua")["categories"] == []


def test_a_reversal_cancels_the_original_out(api):
    bca = account(api, "BCA", balance=1_000_000)

    posted = post(
        api,
        {"type": "expense", "amount": 35_000, "from_account_id": bca, "category": "Makan"},
        IN_OCTOBER,
    )
    api.post(
        f"/transactions/{posted['id']}/reverse", headers={"Idempotency-Key": key()}
    ).raise_for_status()

    assert spending(api, "semua")["expense_total"] == 0


# ----------------------------------------------------------------------
# Periods
# ----------------------------------------------------------------------


def test_only_transactions_inside_the_period_are_counted(api):
    bca = account(api, "BCA", balance=5_000_000)

    post(
        api,
        {"type": "expense", "amount": 100_000, "from_account_id": bca, "category": "Makan"},
        IN_SEPTEMBER,
    )
    post(
        api,
        {"type": "expense", "amount": 35_000, "from_account_id": bca, "category": "Makan"},
        IN_OCTOBER,
    )

    october = spending(api, start="2026-10-01", end="2026-10-31")
    september = spending(api, start="2026-09-01", end="2026-09-30")
    both = spending(api, start="2026-09-01", end="2026-10-31")

    assert october["expense_total"] == 35_000
    assert september["expense_total"] == 100_000
    assert both["expense_total"] == 135_000


def test_a_purchase_just_after_local_midnight_belongs_to_the_new_month(api):
    """1 October 06:00 in Jakarta is 30 September 23:00 UTC."""
    bca = account(api, "BCA", balance=1_000_000)

    post(
        api,
        {"type": "expense", "amount": 20_000, "from_account_id": bca, "category": "Kopi"},
        datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc),
    )

    october = spending(api, start="2026-10-01", end="2026-10-31")
    september = spending(api, start="2026-09-01", end="2026-09-30")

    assert october["expense_total"] == 20_000
    assert september["expense_total"] == 0


def test_an_invalid_period_is_rejected(api):
    r = api.get("/reports/spending", params={"period": "kapan_kapan"})

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_period"


def test_reports_require_a_session(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        assert anon.get("/reports/spending").status_code == 401


def test_reports_are_scoped_to_the_owner(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    bca = account(api, "BCA", balance=1_000_000)
    post(
        api,
        {"type": "expense", "amount": 77_000, "from_account_id": bca, "category": "Makan"},
        IN_OCTOBER,
    )

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "nosy2@example.com", "password": PASSWORD}
        ).raise_for_status()
        assert (
            other.get("/reports/spending", params={"period": "semua"}).json()["expense_total"] == 0
        )


# ----------------------------------------------------------------------
# Income
# ----------------------------------------------------------------------


def test_income_is_reported_as_a_positive_figure(api):
    bca = account(api, "BCA")

    post(
        api,
        {"type": "income", "amount": 5_000_000, "to_account_id": bca, "category": "Gaji"},
        IN_OCTOBER,
    )

    report = spending(api, "semua")

    assert report["income_total"] == 5_000_000
    assert report["expense_total"] == 0


def test_an_opening_balance_is_not_income(api):
    account(api, "BCA", balance=1_000_000)

    assert spending(api, "semua")["income_total"] == 0
