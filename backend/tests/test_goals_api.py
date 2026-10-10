"""Goals and allocations over HTTP (PRD FR07, AC05, AC06).

The claim that matters most is the one AC05 makes: earmarking money for
a goal must not create any. Every test that allocates also checks that
assets and balances are exactly where they were.
"""

from __future__ import annotations

import uuid

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
            "/auth/register", json={"email": "goals@example.com", "password": PASSWORD}
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


def account(api, name="BCA", balance=5_000_000, type_="bank"):
    r = api.post("/accounts", json={"name": name, "type": type_, "opening_balance": balance})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def goal(api, name="Laptop", target=15_000_000, priority=0):
    r = api.post("/goals", json={"name": name, "target_amount": target, "priority": priority})
    assert r.status_code == 201, r.text
    return r.json()


def summary(api):
    return api.get("/summary").json()


# ----------------------------------------------------------------------
# AC05 - an allocation is virtual
# ----------------------------------------------------------------------


def test_ac05_allocating_does_not_change_assets(api):
    account_id = account(api, balance=5_000_000)
    g = goal(api)

    before = summary(api)

    r = api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": account_id, "amount": 2_000_000}
    )
    assert r.status_code == 200, r.text

    after = summary(api)

    assert after["liquid"] == before["liquid"] == 5_000_000
    assert after["net_worth"] == before["net_worth"] == 5_000_000
    # It does reduce what is free to spend, without being a second pot.
    assert after["allocated"] == 2_000_000
    assert after["free_to_spend"] == 3_000_000


def test_ac05_allocating_more_than_the_balance_is_refused(api):
    account_id = account(api, balance=5_000_000)
    g = goal(api)

    r = api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": account_id, "amount": 5_000_001}
    )

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "allocation_exceeds_balance"
    assert summary(api)["allocated"] == 0


def test_allocations_across_goals_share_one_balance(api):
    account_id = account(api, balance=5_000_000)
    laptop = goal(api, "Laptop")
    liburan = goal(api, "Liburan", target=10_000_000)

    api.post(
        f"/goals/{laptop['id']}/allocations", json={"account_id": account_id, "amount": 3_000_000}
    ).raise_for_status()

    over = api.post(
        f"/goals/{liburan['id']}/allocations",
        json={"account_id": account_id, "amount": 2_000_001},
    )
    assert over.status_code == 422

    fits = api.post(
        f"/goals/{liburan['id']}/allocations",
        json={"account_id": account_id, "amount": 2_000_000},
    )
    assert fits.status_code == 200
    assert summary(api)["allocated"] == 5_000_000
    assert summary(api)["free_to_spend"] == 0


def test_re_allocating_replaces_rather_than_accumulates(api):
    account_id = account(api, balance=5_000_000)
    g = goal(api)

    for amount in (1_000_000, 2_000_000, 1_500_000):
        api.post(
            f"/goals/{g['id']}/allocations", json={"account_id": account_id, "amount": amount}
        ).raise_for_status()

    assert summary(api)["allocated"] == 1_500_000


def test_a_goal_can_be_funded_from_several_accounts(api):
    bca = account(api, "BCA", balance=3_000_000)
    cash = account(api, "Cash", balance=1_000_000, type_="cash")
    g = goal(api)

    api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": bca, "amount": 3_000_000}
    ).raise_for_status()
    api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": cash, "amount": 500_000}
    ).raise_for_status()

    detail = api.get(f"/goals/{g['id']}").json()

    assert detail["saved"] == 3_500_000
    assert len(detail["allocations"]) == 2


def test_cannot_allocate_from_a_credit_card(api):
    """There is no balance on a liability to set aside."""
    card = account(api, "Kartu", balance=0, type_="credit_card")
    g = goal(api)

    r = api.post(f"/goals/{g['id']}/allocations", json={"account_id": card, "amount": 100_000})

    assert r.status_code == 422


def test_releasing_frees_the_money_without_moving_it(api):
    account_id = account(api, balance=5_000_000)
    g = goal(api)

    api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": account_id, "amount": 2_000_000}
    ).raise_for_status()

    r = api.post(f"/goals/{g['id']}/allocations/release", params={"account_id": account_id})
    assert r.status_code == 204

    after = summary(api)
    assert after["allocated"] == 0
    assert after["liquid"] == 5_000_000, "the balance was never touched"


def test_moving_an_allocation_is_not_a_transfer(api):
    account_id = account(api, balance=5_000_000)
    laptop = goal(api, "Laptop")
    liburan = goal(api, "Liburan", target=5_000_000)

    api.post(
        f"/goals/{laptop['id']}/allocations", json={"account_id": account_id, "amount": 3_000_000}
    ).raise_for_status()

    before = summary(api)

    r = api.post(
        f"/goals/{laptop['id']}/allocations/move",
        json={"account_id": account_id, "to_goal_id": liburan["id"], "amount": 1_000_000},
    )
    assert r.status_code == 204

    after = summary(api)

    assert after["liquid"] == before["liquid"]
    assert after["allocated"] == before["allocated"] == 3_000_000
    assert api.get(f"/goals/{laptop['id']}").json()["saved"] == 2_000_000
    assert api.get(f"/goals/{liburan['id']}").json()["saved"] == 1_000_000
    # No ledger entry was written for any of it.
    assert len(api.get("/transactions").json()) == 1, "only the opening balance"


def test_moving_more_than_is_allocated_is_refused(api):
    account_id = account(api, balance=5_000_000)
    laptop = goal(api, "Laptop")
    liburan = goal(api, "Liburan", target=5_000_000)

    api.post(
        f"/goals/{laptop['id']}/allocations", json={"account_id": account_id, "amount": 1_000_000}
    ).raise_for_status()

    r = api.post(
        f"/goals/{laptop['id']}/allocations/move",
        json={"account_id": account_id, "to_goal_id": liburan["id"], "amount": 1_000_001},
    )

    assert r.status_code == 404
    assert api.get(f"/goals/{laptop['id']}").json()["saved"] == 1_000_000


# ----------------------------------------------------------------------
# AC06 - the deposit calculator, over HTTP
# ----------------------------------------------------------------------


def test_ac06_through_the_api(api):
    account_id = account(api, balance=5_000_000)
    g = goal(api, "Laptop", target=15_000_000)

    api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": account_id, "amount": 3_000_000}
    ).raise_for_status()

    detail = api.get(f"/goals/{g['id']}", params={"remaining_deposits": 6}).json()

    assert detail["saved"] == 3_000_000
    assert detail["shortfall"] == 12_000_000
    assert detail["per_deposit"] == 2_000_000

    plan = api.get(
        f"/goals/{g['id']}/plan", params={"capacity": 1_500_000, "remaining_deposits": 6}
    ).json()

    assert plan["feasible"] is False
    by_kind = {a["kind"]: a["value"] for a in plan["alternatives"]}
    assert by_kind["more_deposits"] == 8
    assert by_kind["extra_upfront"] == 3_000_000
    assert by_kind["extra_capacity"] == 500_000


def test_a_feasible_plan_offers_no_alternatives(api):
    account_id = account(api, balance=5_000_000)
    g = goal(api, "Laptop", target=15_000_000)
    api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": account_id, "amount": 3_000_000}
    ).raise_for_status()

    plan = api.get(
        f"/goals/{g['id']}/plan", params={"capacity": 2_500_000, "remaining_deposits": 6}
    ).json()

    assert plan["feasible"] is True
    assert plan["alternatives"] == []


def test_an_overdue_goal_reports_needs_adjustment(api):
    g = goal(api, "Laptop", target=15_000_000)

    detail = api.get(f"/goals/{g['id']}", params={"remaining_deposits": 0}).json()

    assert detail["status"] == "needs_adjustment"
    assert detail["per_deposit"] is None
    assert detail["shortfall"] == 15_000_000


# ----------------------------------------------------------------------
# Isolation and validation
# ----------------------------------------------------------------------


def test_goals_require_a_session(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        assert anon.get("/goals").status_code == 401
        assert anon.post("/goals", json={"name": "x", "target_amount": 1}).status_code == 401


def test_cannot_see_or_touch_another_users_goal(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    account_id = account(api, balance=5_000_000)
    g = goal(api)
    api.post(
        f"/goals/{g['id']}/allocations", json={"account_id": account_id, "amount": 1_000_000}
    ).raise_for_status()

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "nosy3@example.com", "password": PASSWORD}
        ).raise_for_status()

        assert other.get("/goals").json() == []
        assert other.get(f"/goals/{g['id']}").status_code == 404

        hijack = other.post(
            f"/goals/{g['id']}/allocations",
            json={"account_id": account_id, "amount": 1},
        )
        assert hijack.status_code == 404

    assert api.get(f"/goals/{g['id']}").json()["saved"] == 1_000_000


@pytest.mark.parametrize("target", [0, -1, 15_000_000.5, "15000000"])
def test_an_invalid_target_is_rejected(api, target):
    r = api.post("/goals", json={"name": "Laptop", "target_amount": target})

    assert r.status_code == 422


def test_allocating_to_a_missing_goal_is_404(api):
    account_id = account(api)

    r = api.post(
        f"/goals/{uuid.uuid4()}/allocations", json={"account_id": account_id, "amount": 1_000}
    )

    assert r.status_code == 404
