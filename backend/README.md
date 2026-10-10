# Duit Akuh — backend

FastAPI ledger for the personal finance app, on PostgreSQL locally and
MySQL/MariaDB in production. Requirements
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
  config.py  db.py    settings from the environment, engine and session
  main.py             FastAPI app, routers, the DomainError -> 422 handler
  domain/             PURE rules, no database - this is where correctness lives
    ledger.py         entry builders, one per event in FR02
    balances.py       FR09 indicators (liquid, net worth, free-to-spend)
    allocations.py    the AC05 "allocations must fit the balance" rule
    goals.py          ceiling division, progress, priority splitting
    budgets.py        limits, overspend, netting
    periods.py        "bulan ini" resolved in the user's timezone
    capacity.py       cash-flow projection (FR10)
    simulation.py     interest and saving plans - uses Fraction, not float
    errors.py         business-rule violations, mapped to 422 by the API
  services/           persistence: idempotency, ownership checks, atomicity
    posting.py drafts.py accounts.py reporting.py export.py …
    chat/             orchestrator.py tools.py dispatch.py confirm.py
    ai/               base.py openai_compat.py fake.py limits.py
  api/                routes_*.py, schemas.py, deps.py (the only auth gate)
alembic/versions/     checked-in migrations; downgrades drop their ENUMs
benchmarks/           103-message Indonesian corpus, runner and watcher
tests/
  test_acceptance_criteria.py   the PRD's ACs as tests - no database needed
  test_posting_integration.py   idempotency, atomicity, isolation - needs a database
  test_auth.py test_chat.py test_goals.py test_budgets.py test_simulation.py …
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

Two engines are supported, and the suite passes on both (354 tests
each). `app/types.py` is the only place that knows the difference — read
its module docstring before changing a column type.

**PostgreSQL** for local work (the better fit for this schema): either one
installed on the machine (port 5432) or the bundled container (port
**5433**, so it cannot clash with a local install):

```sh
docker compose up -d db
```

Either way the service needs a **non-superuser** role and two databases —
one for development, one the test suite drops and recreates tables in.
`setup-db.sql` does that, but it is generated per machine and gitignored,
so recreate it rather than looking for it in git:

```sql
CREATE ROLE duitakuh WITH LOGIN PASSWORD '<generate one>';
CREATE DATABASE duitakuh OWNER duitakuh;
CREATE DATABASE duitakuh_test OWNER duitakuh;
```

```sh
psql -h 127.0.0.1 -U postgres -f setup-db.sql   # as a superuser
```

Then apply the migrations. They are checked in — do not autogenerate the
initial one again:

```sh
.venv/Scripts/alembic upgrade head
```

Downgrades work as well as upgrades, which took an extra step: Alembic
does not drop an ENUM type it created, so a downgrade left the type
behind and the next upgrade failed. Each downgrade drops its own types —
guarded by a dialect check, since MySQL has no standalone enum types.

### MySQL/MariaDB (what production runs)

The deployment target is a shared cPanel host with **MariaDB 10.6** and no
PostgreSQL available, so production uses:

```
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/dbname?charset=utf8mb4
```

`PyMySQL` is the driver — pure Python, so it needs no compiler on a box
that has neither one nor `libmysqlclient`. Create the database as
`utf8mb4`/`utf8mb4_unicode_ci`; cPanel's default is still `latin1`, which
would mangle Indonesian text.

Running the suite against it is worth doing before a release, because a
handful of guarantees are genuinely engine-specific. Point
`TEST_DATABASE_URL` at a MySQL database and leave `APP_ENV` unset or
non-production — `APP_ENV=production` marks the session cookie
`Secure`, which the plain-HTTP test client cannot return, and every
authenticated test then fails with a confusing 401.

The differences that mattered are documented in `app/types.py` and in the
root `CLAUDE.md`: no JSONB, no timezone-aware timestamp, no native UUID
before 10.7, `Identity()` generating nothing (hence the explicit
`AUTO_INCREMENT` on `messages.seq`), CHECK violations arriving as
`OperationalError`, and bulk deletes tripping over self-referencing
`RESTRICT` foreign keys.

## Running it

```sh
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

`GET /health` answers without touching the database — a health check that
fails on a slow query causes restart loops under load.

The browser never calls this port directly. It calls `/api/*` on the
Next.js origin, which proxies here, because the session cookie is
`SameSite=Lax` and would not survive a cross-origin call.

## Tests

```sh
.venv/Scripts/python -m pytest                      # 354 tests
.venv/Scripts/python -m pytest -m "not integration" # pure rules, no database
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
| GET    | `/health`                              | Touches no database, by design                  |
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
| GET    | `/chat/messages`                       | The thread, oldest first                        |
| POST   | `/chat/messages`                       | One complete turn                               |
| POST   | `/chat/messages/stream`                | The same turn as NDJSON                         |
| POST   | `/chat/drafts/{id}/confirm`            | **The only way anything is posted**             |
| POST   | `/chat/drafts/{id}/cancel`             |                                                 |
| GET    | `/reports/spending`                    | `?period=bulan_ini`, by category                |
| GET    | `/goals` `/goals/{id}`                 |                                                 |
| POST   | `/goals`                               |                                                 |
| GET    | `/goals/{id}/plan`                     | `?capacity=…` — the FR11 options                |
| POST   | `/goals/{id}/allocations`              | Earmark, `/release` and `/move` alongside       |
| GET    | `/budgets`                             | Limits, spent, remaining, breaches              |
| DELETE | `/budgets`                             | Removes one category's limit                    |
| POST   | `/simulations/deposit` `/saving`       | Stateless (AC07)                                |
| GET    | `/simulations/capacity`                | Cash-flow projection, not a spending report     |
| GET    | `/export/transactions.csv`             | Streamed, one row per **entry** (AC10)          |

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
back; the reply and any drafts are stored. Bounded at **5 model rounds** —
each is another call on a shared GPU, and an unbounded loop could not
finish inside Cloudflare's window anyway.

**Read tools run immediately; propose tools never write.** A propose
tool stores a `Draft` row with the validated payload and its computed
impact. Confirming posts _from that row_, never from the model's output
again, so what the card showed is what gets written. The draft's
`operation_id` is the idempotency key, which makes a double tap or a
stale card harmless (AC04/AC13).

Thirteen tools are exposed, and **only tools with a working backend**:
a tool the model can call but the server cannot fulfil teaches it to
promise things that fail.

| Reads, no confirmation                                                                                     | Drafts, always confirmed                                                                                                  |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `get_accounts` `get_summary` `get_spending` `get_goals` `get_budgets` `find_transactions` `run_simulation` | `propose_transactions` `propose_account_change` `propose_goal` `propose_allocation` `propose_budget` `propose_correction` |

`build_system_prompt` injects today's date, the weekday, the timezone and
**the user's actual wallet list** into every turn. Both halves were
earned: without the date the model dated "kemarin" to 2023, and without
the wallet list it invented names like `credit_card` and every card case
in the benchmark failed.

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

## Budgets (FR08)

A budget is a **plan for spending, not a claim on cash**. The PRD warns
about this directly, so it is worth stating: setting a budget does not
reduce `free_to_spend`. Only actual spending, and reserves the user
explicitly chooses, do that. There is a test asserting exactly this.

What counts against a budget needs no special-casing — it is the same
expense-account query the period reports use, so transfers and card-bill
payments cannot consume a budget, and refunds free it back up.

`remaining` goes negative and `percent` is uncapped, both deliberately:
an overspend is the one thing a budget exists to surface, so 130% and
−300,000 are shown rather than clamped. The summary nets categories
against each other — which is what "am I within budget overall" means —
but keeps the breached names alongside so a netting can never hide one.

One row per category, recurring monthly, rather than a row per month:
the PRD describes a standing monthly budget, and twelve rows a year
would make "change my food budget" ambiguous about which months it meant.

### A disambiguation the model needed

"makan 850rb pakai BCA" was being read as _setting_ a food budget rather
than recording a purchase, silently overwriting the limit. The tool
descriptions now draw the line explicitly, with a usable heuristic: a
message naming a wallet ("pakai BCA") is a transaction, because budgets
have no wallet. Budget drafts also show the old limit alongside the new
one, so replacing one is visible before it is confirmed.

## Simulation (FR10–FR12, AC07)

`POST /simulations/deposit`, `/saving`, and `GET /simulations/capacity`. Stateless:
a simulation changes nothing until the user applies the plan, and a test
asserts the ledger is byte-identical afterwards.

**`app/domain/simulation.py` uses `Fraction`, not `float` and not even
`Decimal`.** This is the only place in the codebase that handles
fractions of a rupiah, and the PRD asks for intermediate precision with
a single rounding at the end. `float` is the obvious offender, but
`Decimal` fails too once a tenor like 13/12 becomes a decimal early: the
repeating expansion is cut at 28 digits, and 7,500,000 x 3.33% x 13/12 —
exactly 270,562.5 — comes out as 270,562.4999… and rounds to the wrong
rupiah. A `Fraction` keeps 13/12 as 13/12 and divides once, at the end.
`test_a_value_sitting_exactly_on_half_a_rupiah_rounds_up` guards it.

A rate may be a float; an amount may not. A rate is a percentage, parsed
via its repr so 4.25 is read as 17/4, while `principal` and `fees` still
go through the integer-rupiah guards.

An unknown tax rate yields `complete: false`. The arithmetic still runs,
but the PRD forbids presenting a net figure as settled when a component
is missing, so the flag travels with the result.

The capacity model (FR10) is a **cash-flow projection, not a spending
report**, and the difference is deliberate: a card bill counts when it
is paid, and the purchases that formed it are excluded from the same
horizon. Counting both would subtract the same money twice. The
reporting module does the opposite — spending counts at purchase time —
and both are right for their own question.

### A failure worth remembering

The model called `run_simulation` with `months` where the schema said
`periods`. The tool refused, and the model then did the arithmetic
itself — correct that time, by luck. Inventing figures is the one thing
the PRD forbids it, so the tool now accepts either spelling, and every
simulation error tells the model in so many words not to compute it
itself.

## CSV export (AC10)

`GET /export/transactions.csv` takes the same period filters as the
reports, because AC10 requires the export to match the filter the user
applied rather than always dumping everything.

**One row per entry, not per transaction.** A transfer has two sides and
a transfer with a fee has three; collapsing them would force a choice
about which account and amount to show and lose the rest. Entry rows
reconstruct the ledger exactly — a test asserts a transfer's three rows
still sum to zero — and the transaction id ties them together.

Text the user entered is prefixed with an apostrophe when it starts with
`=`, `+`, `-` or `@`, because Excel and Sheets execute such a cell on
open. The data is the user's own, but notes also arrive from chat and,
later, receipt OCR.

The response is streamed; an export is unbounded by nature and the PRD
targets 10,000 transactions per user.

## Rate limiting and queueing (PRD section 13)

`lumi-ai` allows 16 parallel requests **shared with other applications**
and has no SLA, so three limits sit in front of it in
`app/services/ai/limits.py`, each answering a different failure:

| Limit                           | Refusal             | Why                                                                                   |
| ------------------------------- | ------------------- | ------------------------------------------------------------------------------------- |
| 20 messages per minute per user | 429 + `Retry-After` | One person cannot spend everyone's budget                                             |
| One turn in flight per user     | 409                 | A second turn is a double tap, not a second question — queueing it would run it twice |
| 6 concurrent calls, app-wide    | 503 + `Retry-After` | Leaves most of the shared 16 to the other services                                    |

The rate limit counts rows in `ai_request_logs`, which is written for
every call anyway. No extra table, it holds across worker processes, and
it survives a restart. **Failed calls count too** — otherwise a retry
loop is an unmetered way to hammer the GPU.

The queue wait is capped at 20 seconds. Cloudflare drops a request whose
response has not started within 100, so waiting longer produces a 524
the user cannot interpret instead of a sentence they can. The busy
message points at manual entry, as AC22 requires.

The concurrency gate is per process: several uvicorn workers would each
get their own. That is correct for the pilot's single worker, and the
rate limit caps the damage either way; a shared counter would need
Redis.

## Streaming to the browser

`POST /chat/messages/stream` emits newline-delimited JSON: `token` for
each fragment, `tool` when one runs, `draft` when a card is raised,
`reset`, and finally `done`. NDJSON over a plain POST rather than SSE,
because `EventSource` cannot POST and the client already reads the body
as a stream.

`run_turn_events` is the single implementation; the non-streaming
`POST /chat/messages` drains it into one result, so the two cannot
drift apart and all the existing tests kept passing unchanged.

**`reset` exists because narration cannot be withheld.** Tokens are
forwarded the instant they arrive, so by the time a tool call reveals
that the text was the model describing a plan rather than answering, it
has already been shown. `reset` tells the client to drop it instead of
leaving a bubble claiming something happened before it did.

Errors arrive two ways and both matter: as a status code before the
stream opens (rate limited, busy) and as an `error` event once it has.
After the first byte the 200 is long since sent, so a client checking
only the status would read a failed turn as a success.

Measured against the real model: the card appears at 3.0s where the
whole turn takes 4.1s, and for a read question tokens flow from 2.1s to
2.8s rather than arriving in one lump at the end.

## Benchmark

`benchmarks/` holds a 103-message Indonesian corpus and a runner that
measures the two figures the PRD gates the pilot on: ≥90% of drafts
correct on amount, wallet, date and type, and a draft-response p95 under
ten seconds. See `benchmarks/README.md`.

```sh
.venv/Scripts/python -m benchmarks.run     # ~10 minutes against the real model
.venv/Scripts/python -m benchmarks.watch   # live progress, another terminal
```

Latest full run: **93/103 (90.3%), p50 4.16s, p95 6.50s** — both gates
pass, against 76.7% and 12.14s on the first run. The gap was two real
defects, not tuning: the model was never told which wallets the user
had, so it invented names; and spending on a credit card was classified
as paying the card's bill, which would have kept the purchase out of
every report and budget.

It is not part of `pytest`: it costs GPU time on a shared box and needs
a real `LLM_API_KEY`, and the suite must stay runnable without a model.

## Not built yet

- **Deposit schedules.** Goals carry a target date but no deposit dates,
  so `remaining_deposits` is supplied by the caller rather than derived.
- **Voice and receipt OCR** (stage 2). The adapter has `vision` and
  `transcribe` in its interface but no implementation.
- **Automatic benchmark runs.** `benchmarks/` is run by hand; nothing
  gates a commit on it, because CI has no route to the model.
- **A shared concurrency counter.** The app-wide gate is per process, so
  several uvicorn workers would each get their own six. Correct for the
  pilot's single worker; a shared counter would need Redis.
