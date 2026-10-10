"""The money endpoints over HTTP.

The ledger arithmetic is already proven in ``test_acceptance_criteria``.
What matters here is everything the HTTP layer can get wrong on top of
correct arithmetic: a missing idempotency header, a draft that reaches
another user's account, a preview that disagrees with the posting it
previewed, a float amount coerced into an int.
"""

from __future__ import annotations

import uuid

import pytest

from .conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "sangat-rahasia-123"


@pytest.fixture
def api(engine, monkeypatch, reset_tables):
    """TestClient bound to the test database, with a registered user."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "owner@example.com", "password": PASSWORD}
        ).raise_for_status()
        yield client

    reset_tables(factory)


def new_key() -> str:
    return f"key-{uuid.uuid4()}"


def balances(api) -> dict[str, int]:
    return {a["name"]: a["balance"] for a in api.get("/accounts").json()}


def transactions_except_opening(api) -> list[dict]:
    """Creating a funded account posts an opening transaction of its own,
    so tests that count what they posted must exclude it."""
    return [t for t in api.get("/transactions").json() if t["type"] != "opening"]


def make_account(api, name, type_, *, balance=0, alias=None, credit_limit=None):
    body = {"name": name, "type": type_, "opening_balance": balance}

    if alias:
        body["alias"] = alias
    if credit_limit:
        body["credit_limit"] = credit_limit

    response = api.post("/accounts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ----------------------------------------------------------------------
# Authentication is required everywhere
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/accounts"),
        ("post", "/accounts"),
        ("get", "/summary"),
        ("get", "/transactions"),
        ("post", "/transactions"),
        ("post", "/transactions/preview"),
    ],
)
def test_money_endpoints_require_a_session(engine, monkeypatch, method, path):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)

    with TestClient(app) as anon:
        response = anon.get(path) if method == "get" else anon.post(path, json={})

    assert response.status_code == 401, f"{method.upper()} {path} must require a session"


# ----------------------------------------------------------------------
# Accounts
# ----------------------------------------------------------------------


def test_create_account_with_opening_balance(api):
    account = make_account(api, "BCA", "bank", balance=1_000_000, alias="bca")

    assert account["balance"] == 1_000_000
    assert account["debt"] == 0

    summary = api.get("/summary").json()
    assert summary["liquid"] == 1_000_000
    # AC01: an opening balance is not income.
    assert summary["income_total"] == 0


def test_ac01_over_http(api):
    make_account(api, "BCA", "bank", balance=1_000_000)
    make_account(api, "GoPay", "ewallet", balance=100_000)

    summary = api.get("/summary").json()

    assert summary["liquid"] == 1_100_000
    assert summary["net_worth"] == 1_100_000
    assert summary["income_total"] == 0


def test_system_accounts_are_not_listed_as_wallets(api):
    make_account(api, "BCA", "bank", balance=100_000)
    api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": 5_000, "from_account_id": _id(api, "BCA")},
    )

    names = {a["name"] for a in api.get("/accounts").json()}

    assert "BCA" in names
    assert "Lain-lain" not in names, "expense categories are bookkeeping, not wallets"
    assert "Saldo awal" not in names


def _id(api, name: str) -> str:
    return next(a["id"] for a in api.get("/accounts").json() if a["name"] == name)


def test_archiving_hides_an_account_from_liquid_but_keeps_it(api):
    account = make_account(api, "Dompet lama", "cash", balance=50_000)

    api.patch(f"/accounts/{account['id']}", json={"is_archived": True}).raise_for_status()

    assert api.get("/summary").json()["liquid"] == 0
    # Still present - archived, never deleted (FR01).
    assert any(a["id"] == account["id"] for a in api.get("/accounts").json())


def test_cannot_patch_another_users_account(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    victim = make_account(api, "Korban", "bank", balance=500_000)

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "intruder@example.com", "password": PASSWORD}
        ).raise_for_status()
        response = other.patch(f"/accounts/{victim['id']}", json={"name": "Dibajak"})

    assert response.status_code == 404
    assert balances(api) == {"Korban": 500_000}


# ----------------------------------------------------------------------
# Preview
# ----------------------------------------------------------------------


def test_preview_shows_impact_and_writes_nothing(api):
    make_account(api, "BCA", "bank", balance=5_000_000)
    bank_id = _id(api, "BCA")

    before = api.get("/summary").json()

    response = api.post(
        "/transactions/preview",
        json={"type": "expense", "amount": 35_000, "from_account_id": bank_id},
    )

    assert response.status_code == 200
    rows = {r["name"]: r for r in response.json()["impact"]}

    assert rows["BCA"]["before"] == 5_000_000
    assert rows["BCA"]["after"] == 4_965_000
    assert rows["BCA"]["delta"] == -35_000
    assert rows["Lain-lain"]["after"] == 35_000

    # Nothing was saved.
    assert api.get("/summary").json() == before
    assert transactions_except_opening(api) == []


def test_preview_matches_what_posting_actually_does(api):
    """The confirmation card must not promise a different result."""
    make_account(api, "BCA", "bank", balance=1_000_000)
    make_account(api, "GoPay", "ewallet")

    draft = {
        "type": "transfer",
        "amount": 100_000,
        "from_account_id": _id(api, "BCA"),
        "to_account_id": _id(api, "GoPay"),
        "fee": 1_000,
    }

    predicted = {
        r["name"]: r["after"]
        for r in api.post("/transactions/preview", json=draft).json()["impact"]
    }

    api.post("/transactions", headers={"Idempotency-Key": new_key()}, json=draft).raise_for_status()

    actual = {a["name"]: a["balance"] for a in api.get("/accounts").json()}

    assert actual["BCA"] == predicted["BCA"] == 899_000
    assert actual["GoPay"] == predicted["GoPay"] == 100_000


def test_preview_flags_an_overdraft_before_the_user_confirms(api):
    make_account(api, "Cash", "cash", balance=10_000)

    response = api.post(
        "/transactions/preview",
        json={"type": "expense", "amount": 50_000, "from_account_id": _id(api, "Cash")},
    )

    assert response.json()["would_overdraw"] is True


# ----------------------------------------------------------------------
# Posting
# ----------------------------------------------------------------------


def test_posting_requires_an_idempotency_key(api):
    make_account(api, "BCA", "bank", balance=100_000)

    response = api.post(
        "/transactions",
        json={"type": "expense", "amount": 1_000, "from_account_id": _id(api, "BCA")},
    )

    assert response.status_code == 422, "the header is mandatory, not best-effort"
    assert transactions_except_opening(api) == []


def test_ac04_replaying_the_key_over_http_posts_once(api):
    make_account(api, "BCA", "bank", balance=1_000_000)
    key = new_key()
    draft = {"type": "expense", "amount": 35_000, "from_account_id": _id(api, "BCA")}

    first = api.post("/transactions", headers={"Idempotency-Key": key}, json=draft)
    second = api.post("/transactions", headers={"Idempotency-Key": key}, json=draft)

    assert first.status_code == 201
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert first.json()["id"] == second.json()["id"]

    assert len(transactions_except_opening(api)) == 1
    assert balances(api)["BCA"] == 965_000


def test_ac02_over_http(api):
    make_account(api, "BCA", "bank", balance=1_000_000)
    make_account(api, "GoPay", "ewallet")

    api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={
            "type": "transfer",
            "amount": 100_000,
            "from_account_id": _id(api, "BCA"),
            "to_account_id": _id(api, "GoPay"),
            "fee": 1_000,
        },
    ).raise_for_status()

    current = balances(api)
    summary = api.get("/summary").json()

    assert current["BCA"] == 899_000
    assert current["GoPay"] == 100_000
    # Only the fee counts as spending; the transfer itself does not.
    assert summary["expense_total"] == 1_000
    assert summary["income_total"] == 0


def test_ac03_over_http(api):
    make_account(api, "BCA", "bank", balance=2_000_000)
    make_account(api, "Kartu", "credit_card", credit_limit=10_000_000)

    api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={
            "type": "expense",
            "amount": 800_000,
            "from_account_id": _id(api, "Kartu"),
            "category": "Belanja",
        },
    ).raise_for_status()

    assert api.get("/summary").json()["total_debt"] == 800_000

    api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={
            "type": "card_payment",
            "amount": 800_000,
            "from_account_id": _id(api, "BCA"),
            "card_account_id": _id(api, "Kartu"),
        },
    ).raise_for_status()

    summary = api.get("/summary").json()

    assert summary["total_debt"] == 0
    # The decisive assertion: paying the bill did not re-count the spend.
    assert summary["expense_total"] == 800_000


def test_credit_limit_is_not_spendable(api):
    make_account(api, "Kartu", "credit_card", credit_limit=50_000_000)

    summary = api.get("/summary").json()

    assert summary["liquid"] == 0
    assert summary["free_to_spend"] == 0


def test_overdraft_is_refused_then_allowed_with_confirmation(api):
    make_account(api, "Cash", "cash", balance=10_000)
    draft = {"type": "expense", "amount": 50_000, "from_account_id": _id(api, "Cash")}

    refused = api.post("/transactions", headers={"Idempotency-Key": new_key()}, json=draft)
    assert refused.status_code == 422
    assert refused.json()["code"] == "insufficient_balance"

    confirmed = api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={**draft, "allow_negative": True},
    )
    assert confirmed.status_code == 201
    assert balances(api)["Cash"] == -40_000


def test_cannot_post_against_another_users_account(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    victim_account = make_account(api, "Korban", "bank", balance=1_000_000)

    with TestClient(app) as intruder:
        intruder.post(
            "/auth/register", json={"email": "thief@example.com", "password": PASSWORD}
        ).raise_for_status()

        response = intruder.post(
            "/transactions",
            headers={"Idempotency-Key": new_key()},
            json={
                "type": "expense",
                "amount": 1_000_000,
                "from_account_id": victim_account["id"],
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "cross_user_access"
    assert balances(api)["Korban"] == 1_000_000


def test_transactions_list_is_scoped_to_the_owner(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    make_account(api, "BCA", "bank", balance=100_000)
    api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": 1_000, "from_account_id": _id(api, "BCA")},
    ).raise_for_status()

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "nosy@example.com", "password": PASSWORD}
        ).raise_for_status()
        assert other.get("/transactions").json() == []
        assert other.get("/accounts").json() == []


# ----------------------------------------------------------------------
# Money stays integral across the wire (FR03)
# ----------------------------------------------------------------------


@pytest.mark.parametrize("amount", [35_000.5, 0.1, "35000", None, True])
def test_non_integer_amounts_are_rejected(api, amount):
    make_account(api, "BCA", "bank", balance=1_000_000)

    response = api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": amount, "from_account_id": _id(api, "BCA")},
    )

    assert response.status_code == 422, f"{amount!r} must not be accepted as money"


def test_whole_float_is_also_rejected_rather_than_silently_coerced(api):
    """35000.0 is lossless, but accepting it invites 35000.4 next."""
    make_account(api, "BCA", "bank", balance=1_000_000)

    response = api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": 35_000.0, "from_account_id": _id(api, "BCA")},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("amount", [0, -1_000])
def test_non_positive_amounts_are_rejected(api, amount):
    make_account(api, "BCA", "bank", balance=1_000_000)

    response = api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": amount, "from_account_id": _id(api, "BCA")},
    )

    assert response.status_code == 422


# ----------------------------------------------------------------------
# Reversal (FR02, AC08)
# ----------------------------------------------------------------------


def test_reversal_restores_the_balance_and_keeps_both_records(api):
    make_account(api, "BCA", "bank", balance=1_000_000)

    posted = api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": 35_000, "from_account_id": _id(api, "BCA")},
    ).json()

    assert balances(api)["BCA"] == 965_000

    api.post(
        f"/transactions/{posted['id']}/reverse", headers={"Idempotency-Key": new_key()}
    ).raise_for_status()

    assert balances(api)["BCA"] == 1_000_000

    # Both the original and the reversal remain; nothing vanished.
    ids = {t["id"] for t in api.get("/transactions").json()}
    assert posted["id"] in ids
    assert len(ids) == 3, "opening balance + expense + reversal"


def test_a_transaction_cannot_be_reversed_twice(api):
    make_account(api, "BCA", "bank", balance=1_000_000)

    posted = api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": 35_000, "from_account_id": _id(api, "BCA")},
    ).json()

    api.post(
        f"/transactions/{posted['id']}/reverse", headers={"Idempotency-Key": new_key()}
    ).raise_for_status()

    again = api.post(
        f"/transactions/{posted['id']}/reverse", headers={"Idempotency-Key": new_key()}
    )

    assert again.status_code == 409
    assert balances(api)["BCA"] == 1_000_000


def test_cannot_reverse_another_users_transaction(api, engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    make_account(api, "BCA", "bank", balance=1_000_000)
    posted = api.post(
        "/transactions",
        headers={"Idempotency-Key": new_key()},
        json={"type": "expense", "amount": 35_000, "from_account_id": _id(api, "BCA")},
    ).json()

    with TestClient(app) as other:
        other.post(
            "/auth/register", json={"email": "meddler@example.com", "password": PASSWORD}
        ).raise_for_status()
        response = other.post(
            f"/transactions/{posted['id']}/reverse", headers={"Idempotency-Key": new_key()}
        )

    assert response.status_code == 404
    assert balances(api)["BCA"] == 965_000
