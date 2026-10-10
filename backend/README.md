# Duit Akuh — backend

FastAPI + PostgreSQL ledger for the personal finance app. Requirements
live in [`../docs/PRD.md`](../docs/PRD.md); this service owns everything
the PRD calls "fondasi akun dan ledger".

## The one idea worth knowing

The ledger is **double-entry**. Every transaction is a set of entries
whose signed amounts sum to exactly zero, with **debit positive, credit
negative**.

That is not bookkeeping ceremony — it is what turns the PRD's hardest
rules into something that cannot be got wrong by accident:

| Rule                                                | Why it holds                                                                                |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| A transfer is neither income nor expense (AC02)       | It touches only two asset accounts. No income or expense account appears in the transaction. |
| A card payment does not re-count the purchase (AC03)  | The purchase debited an expense; the payment debits the *liability*. The expense is untouched. |
| An opening balance is not income (AC01)               | It credits a system **equity** account, not income.                                          |
| An allocation cannot inflate assets (AC05)            | Allocations write no entry at all. They are an earmark on an existing balance.               |

Amounts are **integer rupiah** everywhere (`BIGINT`). `app/money.py`
refuses floats that are not exactly integral, so a lost-precision value
raises instead of quietly rounding (FR03).

## Layout

```
app/
  money.py            integer-rupiah guards
  models.py           SQLAlchemy schema; the sign convention is documented here
  domain/             PURE rules, no database - this is where correctness lives
    ledger.py         entry builders, one per event in FR02
    balances.py       FR09 indicators (liquid, net worth, free-to-spend)
    allocations.py    the AC05 "allocations must fit the balance" rule
    errors.py         business-rule violations, mapped to 422 by the API
  services/           persistence: idempotency, ownership checks, atomicity
  main.py             FastAPI app
tests/
  test_acceptance_criteria.py   the PRD's ACs as tests - no database needed
  test_posting_integration.py   idempotency, atomicity, isolation - needs PostgreSQL
```

`domain/` is pure on purpose: the money rules are the part that has to be
provably right, so they are testable without a database, a user, or a
network.

## Setup

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

cp .env.example .env     # then fill in
```

Requires Python 3.11+ (developed on 3.12).

## Database

```sh
docker compose up -d db          # PostgreSQL 17 on port 5433
```

Port 5433 avoids clashing with a PostgreSQL installed directly on the
machine. Point `DATABASE_URL` elsewhere if you already have one.

Then create the initial migration (once, against a live database) and
apply it:

```sh
.venv/Scripts/alembic revision --autogenerate -m "initial schema"
.venv/Scripts/alembic upgrade head
```

## Tests

```sh
.venv/Scripts/python -m pytest                      # everything available
.venv/Scripts/python -m pytest -m "not integration" # pure rules only, no database
```

The integration tests **skip** rather than fail when `TEST_DATABASE_URL`
is unset, so the domain suite runs anywhere. They create and drop tables,
so that URL must never point at a database holding real data.

```sh
.venv/Scripts/python -m ruff check .
```

## Not built yet

- **Authentication.** Until email/password auth exists there are no money
  endpoints, because AC08 makes per-owner authorization a release gate and
  an unauthenticated financial API is not worth shipping even briefly.
- **The chat orchestrator** and the adapter for the self-hosted `lumi-ai`
  service (PRD section 13). Config keys are already read in `config.py`.
- **Goals, budgets, simulation.** The `Goal` and `Allocation` tables and the
  allocation rule exist; the services on top do not.
