"""Dates that arrive from a client without an offset.

JSON has no datetime, so ``"2027-04-30"`` and ``"2026-10-10T14:30:00"``
both reach us as naive values. The column type refuses those outright
(``app.types.UtcDateTime``) because at that depth the instant really is
ambiguous and a wrong one in a ledger is unrecoverable — but refusing
there surfaces to the caller as a 500, not as a stored row and not as a
422 either.

So the edge resolves the ambiguity before storage: a wall-clock time
means the owner's own clock. These tests pin that the three endpoints
that take a datetime accept one without an offset, and that reading it
back in the owner's timezone returns the date they typed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "sangat-rahasia-123"
JAKARTA = ZoneInfo("Asia/Jakarta")


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
            "/auth/register", json={"email": "naive@example.com", "password": PASSWORD}
        ).raise_for_status()
        yield client

    reset_tables(factory)


# ----------------------------------------------------------------------


def test_a_date_only_goal_deadline_is_accepted(api):
    response = api.post(
        "/goals",
        json={"name": "Laptop", "target_amount": 15_000_000, "target_date": "2027-04-30"},
    )

    assert response.status_code == 201, response.text


def test_a_deadline_is_stored_as_local_midnight(api):
    """A deadline is a day, and the day starts where the owner is.

    Both readings of "2027-04-30" — Jakarta midnight and UTC midnight —
    happen to render as the 30th in WIB, so the date alone would not
    tell them apart. The instant does: 17:00 UTC on the 29th is the
    start of the 30th in Jakarta, and anything else is seven hours of
    somebody else's day.
    """
    api.post(
        "/goals",
        json={"name": "Laptop", "target_amount": 15_000_000, "target_date": "2027-04-30"},
    ).raise_for_status()

    stored = datetime.fromisoformat(api.get("/goals").json()[0]["target_date"])

    assert stored.astimezone(timezone.utc) == datetime(2027, 4, 29, 17, 0, tzinfo=timezone.utc)
    assert stored.astimezone(JAKARTA).date().isoformat() == "2027-04-30"


def test_a_naive_transaction_time_is_accepted(api):
    wallet = api.post(
        "/accounts", json={"name": "BCA", "type": "bank", "opening_balance": 1_000_000}
    ).json()

    response = api.post(
        "/transactions",
        headers={"Idempotency-Key": f"naive-{uuid.uuid4()}"},
        json={
            "type": "expense",
            "amount": 35_000,
            "from_account_id": wallet["id"],
            "occurred_at": "2026-10-10T14:30:00",
        },
    )

    assert response.status_code == 201, response.text


def test_a_naive_transaction_time_is_read_as_local(api):
    wallet = api.post(
        "/accounts", json={"name": "BCA", "type": "bank", "opening_balance": 1_000_000}
    ).json()

    api.post(
        "/transactions",
        headers={"Idempotency-Key": f"naive-{uuid.uuid4()}"},
        json={
            "type": "expense",
            "amount": 35_000,
            "from_account_id": wallet["id"],
            "occurred_at": "2026-10-10T14:30:00",
        },
    ).raise_for_status()

    posted = next(row for row in api.get("/transactions").json() if row["type"] == "expense")
    local = datetime.fromisoformat(posted["occurred_at"]).astimezone(JAKARTA)

    assert (local.hour, local.minute) == (14, 30)
    assert local.date().isoformat() == "2026-10-10"


def test_a_naive_opening_date_is_accepted(api):
    response = api.post(
        "/accounts",
        json={
            "name": "Tunai",
            "type": "cash",
            "opening_balance": 250_000,
            "occurred_at": "2026-10-01",
        },
    )

    assert response.status_code == 201, response.text


def test_an_offset_is_respected_rather_than_reinterpreted(api):
    """An explicit offset is the caller's answer, not ours to override."""
    wallet = api.post(
        "/accounts", json={"name": "BCA", "type": "bank", "opening_balance": 1_000_000}
    ).json()

    api.post(
        "/transactions",
        headers={"Idempotency-Key": f"aware-{uuid.uuid4()}"},
        json={
            "type": "expense",
            "amount": 35_000,
            "from_account_id": wallet["id"],
            # 09:00 UTC is 16:00 in Jakarta. Reinterpreting it as local
            # would have stored 02:00 UTC instead.
            "occurred_at": "2026-10-10T09:00:00+00:00",
        },
    ).raise_for_status()

    posted = next(row for row in api.get("/transactions").json() if row["type"] == "expense")
    stored = datetime.fromisoformat(posted["occurred_at"]).astimezone(timezone.utc)

    assert (stored.hour, stored.minute) == (9, 0)
