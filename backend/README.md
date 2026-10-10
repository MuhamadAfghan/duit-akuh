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

| Rule                                                 | Why it holds                                                                                   |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| A transfer is neither income nor expense (AC02)      | It touches only two asset accounts. No income or expense account appears in the transaction.   |
| A card payment does not re-count the purchase (AC03) | The purchase debited an expense; the payment debits the _liability_. The expense is untouched. |
| An opening balance is not income (AC01)              | It credits a system **equity** account, not income.                                            |
| An allocation cannot inflate assets (AC05)           | Allocations write no entry at all. They are an earmark on an existing balance.                 |

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
.venv/Scripts/python -m pytest                      # 90 tests
.venv/Scripts/python -m pytest -m "not integration" # 38, pure rules, no database
```

The integration tests **skip** rather than fail when `TEST_DATABASE_URL`
is unset, so the domain suite runs anywhere. They create and drop tables,
so that URL must never point at a database holding real data.

```sh
.venv/Scripts/python -m ruff check .
```

## Authentication

Email + password, with **server-side sessions in an httpOnly cookie** —
not a JWT in JavaScript. Three reasons: page scripts cannot read the
cookie, so an XSS bug cannot steal a login; logout genuinely revokes,
which a stateless token cannot; and no credential is ever in a response
body, matching the principle behind AC21.

- Passwords: **Argon2id**, individually salted, re-hashed on sign-in when
  the cost parameters change.
- Session tokens: 256 bits of randomness, **stored only as a SHA-256
  hash**, so a database leak yields nothing usable. A fast hash is right
  here — the token is already high-entropy, and a slow KDF would just add
  latency to every request.
- Sign-in failures are uniform: wrong password and unknown address return
  the same error, and an unknown address still pays for one Argon2
  verification so timing does not reveal who has an account.
- Throttling (PRD section 9): 8 failures within 15 minutes locks further
  attempts, including for addresses that do not exist — otherwise the
  lockout itself would be an enumeration oracle.
- Changing a password revokes every existing session.

`deps.get_current_user` is the single gate for authenticated endpoints.
There is deliberately **no development bypass**: a bypass that exists in
the code is a bypass that can ship.

### A bug worth remembering

Throttling was initially dead code. Failed attempts were recorded in the
request's session, the handler then raised, and `get_db` rolled the
session back — so the counter never incremented in the running app, even
though the service-level test passed. The login handler now commits the
attempt before raising, and `test_throttling_actually_applies_over_http`
guards it. Any future control that must persist across a _failed_
request needs the same care.

## Endpoints

| Method | Path                                   | Notes                                           |
| ------ | -------------------------------------- | ----------------------------------------------- |
| POST   | `/auth/register` `/auth/login`         | Sets the session cookie                         |
| POST   | `/auth/logout` `/auth/change-password` | Both revoke sessions                            |
| GET    | `/auth/me`                             |                                                 |
| GET    | `/accounts`                            | Wallets with balances; system accounts excluded |
| POST   | `/accounts`                            | Optional opening balance, posted as equity      |
| PATCH  | `/accounts/{id}`                       | Rename, alias, limit, archive. No delete (FR01) |
| GET    | `/summary`                             | The FR09 indicators                             |
| POST   | `/transactions/preview`                | Impact only — writes nothing                    |
| POST   | `/transactions`                        | Requires `Idempotency-Key`                      |
| GET    | `/transactions`                        |                                                 |
| POST   | `/transactions/{id}/reverse`           | Posts the mirror image; deletes nothing         |

Two things are load-bearing:

**`Idempotency-Key` is mandatory on posting**, not best-effort. AC04
requires a confirmation sent twice to produce exactly one transaction; a
client that forgot the header would silently lose that guarantee, so a
missing header is a 422. Replaying a key returns the original with
`replayed: true`.

**Preview and posting build legs through the same code path**
(`services/drafts.py`), so the impact shown on the confirmation card
cannot disagree with what gets written. `test_preview_matches_what_posting_actually_does`
pins that.

Amounts are `StrictInt` on the wire. Without it Pydantic would coerce
`35000.4` to an int and round money away, so even a lossless `35000.0`
is rejected — accepting it invites `35000.4` next.

## Chat orchestrator

`services/chat/` turns a sentence into a confirmed transaction.

One turn: the user's message plus a recent window of the thread goes to
the model with the tool list; tool calls are executed; results are fed
back; the reply and any drafts are stored. Bounded at 3 model rounds —
each is another call on a shared GPU, and an unbounded loop could not
finish inside Cloudflare's window anyway.

**Read tools run immediately; propose tools never write.** A propose
tool stores a `Draft` row with the validated payload and its computed
impact. Confirming posts _from that row_, never from the model's output
again, so what the card showed is what gets written. The draft's
`operation_id` is the idempotency key, which makes a double tap or a
stale card harmless (AC04/AC13).

Only tools with a working backend are exposed. `run_simulation`,
`propose_goal`, `propose_allocation` and `propose_budget` from the PRD's
table are deliberately absent — a tool the model can call but the server
cannot fulfil teaches it to promise things that fail.

Model output is **untrusted data, not instruction**. The dispatcher
re-validates every field, re-resolves account names through the same
ambiguity rules the REST API uses, and recomputes every figure from the
database. An ambiguous name returns an error to the model so it asks the
user, rather than picking one (AC04).

`services/ai/` holds the adapter. `OpenAiCompatAdapter` talks to vLLM;
`FakeAdapter` scripts turns for tests, so the orchestrator runs with no
network, GPU or API key.

**Requests are streamed.** Not for UI smoothness: Cloudflare returns 524
if a response has not _started_ within 100 seconds, and a queued
generation on a shared GPU can exceed that before its first token.

An outage degrades rather than failing — the reply becomes a plain
message pointing at manual entry, and the user's text is still saved
(AC09/AC22).

### Verified against the real model

Connected to `lumi-ai` (`qwen3.5-9b`, `max_model_len` 24576) on
2026-10-10. Round-trip latency 1.5-4.5s per model round. Indonesian
informal amounts parse correctly: "35rb" -> 35000, "100 ribu" ->
100000, "kemarin" sets the date.

Two problems showed up only with the real model, both now fixed:

**The model stopped calling tools after a few turns.** History contained
only its prose replies, with no evidence that tools had ever been
used, so it copied the pattern — replying "Draft transaksi: ..." in
text while creating no draft at all. The user saw a message claiming a
draft that did not exist. Card turns in history now state explicitly
that a tool produced them, and the system prompt leads with the rule.
In isolation the same message had always worked, which is why only a
multi-turn test caught it.

**Three tool rounds was exactly the ceiling.** A plain "top up X from Y"
uses get_accounts, then propose_transactions, then the reply. Anything
needing one more lookup was silently cut off. Now five.

Also tightened: `get_summary` returns all-time totals with no period
filter, and the model was labelling them "bulan ini". The tool
description now says so, and the model answers honestly instead.

## Periods (FR06)

`GET /reports/spending?period=bulan_ini` and the `get_spending` tool
answer "bulan ini makan berapa" with a category breakdown.

Ranges are resolved in the **user's timezone**, in
`app/domain/periods.py`. That is the whole difficulty: Jakarta is UTC+7,
so October begins at 17:00 UTC on 30 September. A UTC month boundary
would file a 06:00 purchase on 1 October into the previous month. Ranges
are half-open so a transaction at exactly midnight belongs to one period
only.

What counts as spending needs no special-casing — it falls out of
double entry. A query restricted to expense accounts cannot see
transfers (they touch only assets) or card payments (they debit a
liability), and a refund credits its expense account so it nets off on
its own.

`semua` is unbounded at both ends on purpose: capping it at today would
hide a transaction accidentally dated in the future, which is the one
view meant to show everything.

Balances stay out of this endpoint. A balance is a point in time, not a
range, and putting both in one response invites reading a month's
spending as if it were a balance.

## Goals and allocations (FR07, AC05, AC06)

An allocation is an **earmark on money already in an account**. It writes
no ledger entry, so it cannot change net assets — AC05 holds
structurally, not by a check. What does need checking is over-promising:
the total earmarked on an account may not exceed its positive balance,
and moving an earmark between goals is explicitly not a transfer.

`app/domain/goals.py` holds the arithmetic, pure:

- The required deposit is **ceiling-divided**. Three deposits of 3,333 do
  not reach 10,000; being slightly early beats being short on the
  deadline.
- An overdue goal returns `needs_adjustment` with `per_deposit: null`
  rather than dividing by zero or inventing a schedule.
- Progress caps at 100 and any excess is reported as `surplus`, because a
  bar past full says nothing.
- `split_capacity_by_priority` never recommends more in total than the
  user can save; later goals get what is left, not what they asked for.

`GET /goals/{id}/plan?capacity=…` answers FR11. The PRD's worked example
runs exactly: a Rp15,000,000 goal with Rp3,000,000 saved over six
deposits needs Rp2,000,000 each, and a capacity of Rp1,500,000 offers
eight deposits, Rp3,000,000 more up front, or Rp500,000 more per period.

## Not built yet

- **Budgets and simulation** (FR08, FR10–FR12).
- **Deposit schedules.** Goals carry a target date but no deposit dates,
  so `remaining_deposits` is supplied by the caller rather than derived.
- **Voice and receipt OCR** (stage 2). The adapter has `vision` and
  `transcribe` in its interface but no implementation.
- **Per-user rate limiting and a queue.** `lumi-ai` allows 16 parallel
  requests shared with other apps; nothing enforces a share yet.
- **Streaming to the browser.** The adapter streams from vLLM, but
  `/chat/messages` returns one complete turn.
