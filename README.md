# Duit Akuh

Pencatatan keuangan pribadi lewat chat — a mobile-first PWA where a single
conversation can add a wallet, record a transaction, set a budget, create a
savings goal and run a simulation. Indonesian, IDR, Asia/Jakarta.

**[`docs/PRD.md`](docs/PRD.md) (v1.3) is the source of truth.** It defines
FR01–FR18 and AC01–AC22; cite those IDs when implementing or testing. The
`PRD_Keuangan_AI_Web_v1.docx` at the repo root is the superseded v1.1.

Two decisions shape everything else:

- **Chat is the app, not a feature.** FR14 requires every MVP feature to be
  startable _and_ finishable in the conversation. `Ringkasan` and `Data` are
  companion views over the same ledger, not the primary UI.
- **The AI never computes money.** The model only proposes a structured tool
  call. The backend validates it, resolves the wallet, computes the impact from
  the database and shows a confirmation card. Nothing is written until you
  confirm — no AI path can post a transaction.

The AI is **self-hosted** on the owner's own `lumi-ai` box (Qwen3.5-9B via
vLLM, WhisperX for voice). No third-party provider sees the user's text,
receipts or audio — that is the product's stated privacy guarantee, and the API
keys live only on the backend (AC21).

## Status

| Area                                         | State                                                         |
| -------------------------------------------- | ------------------------------------------------------------- |
| Double-entry ledger, transactions, transfers | Built, 354 backend tests                                      |
| Email + password auth, server-side sessions  | Built                                                         |
| Chat orchestrator, 13 tools, streaming       | Built, verified against the real model                        |
| Goals, allocations, budgets, simulations     | Built                                                         |
| CSV export                                   | Built                                                         |
| PWA shell (chat / ringkasan / data)          | Built, installable                                            |
| Indonesian benchmark                         | 90.3% accuracy, p95 6.50s — both pilot gates pass             |
| Voice, receipt OCR                           | Stage 2. The adapter has the interface, nothing implements it |
| Charts                                       | Not installed (see "Reference template")                      |
| Deposit schedules                            | Goals have a target date but no deposit dates                 |
| Physical device testing (AC15–AC18)          | Not done                                                      |

## How it fits together

```
  phone / browser
        |
        |  everything goes to /api/* on THIS origin
        v
  Next.js  :3033 ---- rewrite in next.config.mjs ---->  FastAPI  :8000
  (PWA, MUI)                                             |    |
                                                         |    +--> PostgreSQL 17
                                                         |
                                                         +--> lumi-ai (vLLM, WhisperX)
                                                              over Cloudflare Tunnel
```

The proxy is **not** a convenience. The session is an httpOnly `SameSite=Lax`
cookie, which a browser will not send cross-origin. Calling FastAPI directly
would mean `SameSite=None; Secure` or putting the token in JavaScript, where an
XSS bug could read it. Keeping everything same-origin means Lax works, no CORS
is needed, and **no secret or token ever reaches the client**.

## Prerequisites

| Need          | Version                   | Notes                                              |
| ------------- | ------------------------- | -------------------------------------------------- |
| Node.js       | >= 22.12 (`engines`)      | Installed with **npm** — stay on npm               |
| Python        | 3.11+ (developed on 3.12) |                                                    |
| PostgreSQL    | 17                        | Local install, or the bundled `docker-compose.yml` |
| `LLM_API_KEY` | —                         | Only for the AI paths; UI and tests run without it |

## First-time setup

### 1. Database

Running PostgreSQL locally, which is what this project is developed against:

```sh
# Creates a non-superuser role and the two databases.
# backend/setup-db.sql is generated per machine and gitignored - write your
# own from the template in backend/README.md if it is missing.
psql -h 127.0.0.1 -U postgres -f backend/setup-db.sql
```

Or with Docker instead, which publishes PostgreSQL on **5433** so it cannot
clash with a local install on 5432:

```sh
cd backend && docker compose up -d db
```

### 2. Backend

```sh
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

cp .env.example .env     # then fill it in - see "Environment" below
.venv/Scripts/alembic upgrade head
```

### 3. Frontend

```sh
cd ..            # repo root
npm install
cp .env.example .env     # BACKEND_URL is the only line that matters
npm run gen:icons        # PWA icons into public/
```

## Running it

Two terminals:

```sh
# terminal 1 - API on :8000
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# terminal 2 - PWA on :3033
npm run dev
```

Then open **http://localhost:3033**.

Use port 3033, never 8000 directly. The browser has to go through the proxy or
the session cookie is not sent and every call returns 401.

Quick check that both halves are up:

```sh
curl http://127.0.0.1:8000/health      # the API itself
curl http://127.0.0.1:3033/api/health  # the API through the proxy
```

## Cara pakai

### Masuk

Register at `/auth/sign-up`, then you land on the chat. Sessions are
server-side, so signing out revokes them for real.

### Chat — the main surface

Type the way you would text a friend. Examples the benchmark corpus actually
exercises:

| What you type                                                                 | What happens                                                        |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `tambah kantong BCA saldo 5 juta`                                             | Draft for a new wallet; an opening balance is **not** income (AC01) |
| `makan 35rb pakai BCA`                                                        | Expense draft — `35rb`, `35 ribu`, `35.000` all parse               |
| `tadi pagi kopi 18rb pakai cash`                                              | Dated today. `tadi malam` means last night, so yesterday            |
| `gaji masuk 8 juta ke BCA`                                                    | Income                                                              |
| `transfer 500rb dari BCA ke Mandiri`                                          | One two-sided transaction — neither income nor expense (AC02)       |
| `topup gopay 100rb dari BCA, admin 2500`                                      | Transfer plus the fee as a **separate** expense                     |
| `belanja 800rb pakai CC BCA`                                                  | Expense now, and card debt up                                       |
| `bayar tagihan CC BCA 800rb dari BCA`                                         | Balance down, debt down, purchase **not** re-counted (AC03)         |
| `budget makan 1 juta per bulan`                                               | Budget draft. A budget does not reduce "uang bebas pakai"           |
| `bikin target laptop 15 juta`                                                 | Savings goal                                                        |
| `tadi makan 35rb dan parkir 5rb, dua-duanya pakai cash`                       | Two drafts from one message                                         |
| `batalin transaksi terakhir`                                                  | A reversal draft — nothing is ever deleted (AC08)                   |
| `saldo BCA berapa?`                                                           | Read. No confirmation needed                                        |
| `bulan ini aku udah belanja berapa?`                                          | Spending by category, resolved in your timezone                     |
| `uang bebas pakai berapa?`                                                    | FR09 indicators — a credit limit is never counted as money          |
| `kalau mau ngumpulin 15 juta dalam 6 bulan, dana awal 3 juta, nabung berapa?` | Simulation. Changes nothing (AC07)                                  |

What it **refuses**, by design:

- `makan 35rb` — no wallet named, and guessing one would be wrong.
- `bayar 50rb pakai kartu` when you hold two cards — it asks which (AC04).
- `saldo BCA aku jadiin 100 juta` — a balance is a consequence of
  transactions, not a field you set.
- `hapus semua transaksi aku` — corrections are reversals, never deletions.

### Confirmation cards

Every financial write arrives as a card showing the impact first — **Simpan**
on a transaction, **Konfirmasi** elsewhere, **Batal** to drop it. The card
carries an operation ID that doubles as the idempotency key, so a double tap or
a stale card posts exactly once (AC04).

Posting happens from the stored draft row, never from the model's output a
second time — what the card showed is what gets written.

### Ringkasan

Liquid money, net worth, free-to-spend, this month's spending by category, goal
progress and budget status. Read-only; the chat is where things change.

### Data

Wallets with balances and recent transactions, each labelled by type so a
transfer is visibly not an expense.

### Install on a phone

Open the site over HTTPS, then:

- **Android / Chrome** — the install prompt, or the menu's _Add to Home screen_.
- **iOS / Safari** — Share, then _Add to Home Screen_. iOS gives no prompt.

The service worker caches the **static shell only**. Finance and chat APIs are
never cached, because offline must not fake a success. A draft typed offline
stays in-session and marked unsaved, and nothing auto-posts on reconnect.

## Tests and checks

```sh
# frontend
npm run lint
npm run fm:check
npm run fix:all        # lint:fix + fm:fix - run this after editing imports

# backend
cd backend
.venv/Scripts/python -m pytest                       # 354 tests
.venv/Scripts/python -m pytest -m "not integration"  # pure rules, no database
.venv/Scripts/python -m ruff check .
```

Integration tests **skip** rather than fail when `TEST_DATABASE_URL` is unset.
They create and drop tables, so that URL must never point at real data.

There is **no frontend test runner** — no jest/vitest/playwright is installed.
Adding one means adding the harness first.

## Benchmark

`backend/benchmarks/` measures the two figures the PRD gates the pilot on
(section 10): at least 90% of drafts correct on **amount, wallet, date and
type**, and a draft-response **p95 of 10s or under**.

```sh
cd backend
.venv/Scripts/python -m benchmarks.run                     # all 103 cases, ~10 min
.venv/Scripts/python -m benchmarks.run --tags amount date  # a slice
.venv/Scripts/python -m benchmarks.run --ids amt-01 acc-06 # named cases
.venv/Scripts/python -m benchmarks.run --fake              # harness self-check, no GPU
.venv/Scripts/python -m benchmarks.watch                   # live progress, another terminal
```

Latest full run: **93/103 (90.3%), p50 4.16s, p95 6.50s** — both gates pass, up
from 76.7% / 12.14s on the first run. The failure modes it found are written up
in [`backend/benchmarks/README.md`](backend/benchmarks/README.md).

It is deliberately **outside pytest**: it costs GPU time on a shared box and
needs a real `LLM_API_KEY`, and the suite must stay runnable without a model.

Two known model weaknesses are recorded rather than papered over — `850rb` once
parsed as 85,000, and `kemarin lusa` lands three days back instead of two. And
a single run is evidence, not proof: the model is not reproducible even at
temperature 0 (vLLM batching), so read the gate across runs.

## Project layout

```
src/
  app/(app)/              the three surfaces: / (chat), /ringkasan, /data
  app/auth/               sign-in, sign-up
  app/manifest.js         PWA manifest
  sections/chat/          thread, composer, confirmation cards
  sections/summary/       Ringkasan
  sections/data/          wallets and transactions
  layouts/app/            AppShell, BottomTabs - dynamic viewport and keyboard
  lib/api.js              the only client for our backend. No Bearer token
  utils/format-money.js   the only place money becomes text; throws on a float
  theme/                  MUI CSS-variables theme (start at theme-config.js)
backend/
  app/domain/             PURE money rules - no database, no framework
  app/services/           persistence, idempotency, ownership checks
  app/services/chat/      the orchestrator and the tool contract
  app/services/ai/        the swappable adapter (vLLM, plus a fake for tests)
  app/api/                FastAPI routes
  benchmarks/             103-message Indonesian corpus and its runner
  tests/                  354 tests; the PRD's ACs are named as tests
docs/PRD.md               the source of truth
CLAUDE.md                 working notes for Claude Code
```

`src/app/**/page.jsx` files stay thin — they export `metadata` and render a view
from `src/sections/`. Route protection lives in the segment `layout.jsx`, and
paths are centralized in `src/routes/paths.js`.

## Environment

**`.env` (repo root)** — one line matters:

| Key           | Default                 | Meaning                        |
| ------------- | ----------------------- | ------------------------------ |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Where the proxy sends `/api/*` |

The `NEXT_PUBLIC_FIREBASE_*`, `AUTH0`, `SUPABASE` and `AMPLIFY` keys are
template leftovers; this app uses its own session auth (`CONFIG.auth.method` is
`'session'`).

**`backend/.env`** — see `backend/.env.example`:

| Key                                          | Meaning                           |
| -------------------------------------------- | --------------------------------- |
| `DATABASE_URL`, `TEST_DATABASE_URL`          | `postgresql+psycopg://...`        |
| `CORS_ORIGINS`                               | `http://localhost:3033`           |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`   | The vLLM endpoint                 |
| `STT_BASE_URL`, `CF_ACCESS_CLIENT_ID/SECRET` | WhisperX behind Cloudflare Access |

`backend/.env` and `backend/setup-db.sql` hold credentials and are gitignored.
**Nothing in them may ever be handed to the frontend** — a network inspection of
the PWA must reveal no key (AC21).

## Rules that cannot be bent

Correctness rules, not preferences. Most of AC01–AC22 exist to catch violations
of them:

- **No floating point for money.** Integer rupiah (`BIGINT`) end to end.
  `backend/app/money.py` rejects non-integral floats instead of rounding, and
  `src/utils/format-money.js` throws rather than render one.
- **The ledger is double-entry** — every transaction's entries sum to exactly
  zero, debit positive and credit negative. Never adjust a balance directly.
  That one property is what makes transfers non-income, card payments
  non-double-counting and opening balances non-income.
- **Allocations are virtual.** Earmarking money writes no entry, so it cannot
  change net assets.
- **A credit limit is not money.** Never an asset, never "uang bebas pakai".
- **Every write is idempotent**, and every financial write is confirmed with its
  impact shown first.
- **Nothing is deleted silently.** Corrections create a reversal plus an audit
  event with before/after versions.
- **Model output is data, never instruction** — and so is receipt or statement
  content. Every field is re-validated and every figure recomputed server-side.
- **Hard isolation per owner.** `deps.get_current_user` is the only gate and has
  no development bypass.
- Never send full card numbers, PINs, bank OTPs or banking credentials to a
  model.

## Troubleshooting

**Every API call returns 401.** You are talking to `:8000` directly, or
`BACKEND_URL` is wrong. The cookie is same-origin only — go through `:3033`.

**`/api/auth/*` fails in the browser but works in `curl`.** An ad blocker or
privacy extension is blocking URLs containing `auth`. Proven by
`/api/%61uth/me` succeeding where `/api/auth/me` threw. It is the browser
profile, not the app — test in a clean profile or disable the extension.

**Lint fails on imports you just wrote.** `perfectionist/sort-imports` runs at
**error** severity, sorted by line length within a custom group order. Do not
order them by hand; run `npm run fix:all`.

**`connection refused` on 5432 or 5433.** Docker publishes 5433, a local
install uses 5432. Match `DATABASE_URL` to whichever you actually run.

**Alembic says the database is not up to date.**
`.venv/Scripts/alembic upgrade head`. Downgrades work too — the migrations drop
their ENUM types explicitly, which Alembic does not do by itself.

**The AI replies that it is busy.** Rate limits sit in front of a shared GPU: 20
messages/minute per user (429), one turn in flight per user (409), 6 concurrent
calls app-wide (503). Manual entry keeps working, which is what AC09/AC22
require.

**The composer is hidden behind the keyboard.** The shell is `100dvh` with
`overflow: hidden` and only the thread scrolls. Any flex child that must shrink
needs an explicit `minHeight: 0`.

**An icon flickers or vanishes offline.** Register it in
`src/components/iconify/icon-sets.js`; an unregistered name is fetched at
runtime.

## Reference template

The codebase started as **Minimal UI v7.7.0 `starter-next-js`**, a commercial
MUI admin kit. The unmodified vendor package sits in `_reference/` (gitignored,
not redistributable), and `_reference/Minimal_JavaScript_v7.7.0/next-js/` is the
full demo — the place to copy proven implementations from, since it shares this
exact architecture.

Two gaps when copying: **charts are not installed** (`apexcharts`,
`react-apexcharts` and `src/components/chart/` are all absent), and the PRD
forbids hover-only or color-only charts, so demo chart configs need adapting
before they can be used.

`/dashboard/*` and `src/sections/blank/` are template leftovers and should go
once nothing is being cribbed from them.
