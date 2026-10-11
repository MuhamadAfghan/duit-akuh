# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Web pencatatan keuangan pribadi berbasis AI, for Indonesian users (IDR, Bahasa Indonesia, Asia/Jakarta).

Requirements: **`docs/PRD.md` (v1.3) is the source of truth.** It defines FR01–FR18 and AC01–AC22 — cite those IDs when implementing or testing. The `PRD_Keuangan_AI_Web_v1.docx` still at the repo root is the superseded **v1.1** and should not be read; v1.3 adds the AI service spec (section 13) and the PWA/mobile mandate (section 12).

**The product is chat-first and mobile-first.** The chat is the main surface and must be able to start _and finish_ every feature in a release (FR14). It is no longer a single thread: a user has named, pinnable, archivable conversations, and the server always resolves one so nobody has to pick before they can type. The dashboard is a companion view over the same data, not the primary UI. A mobile-first **PWA is mandatory for MVP** (FR16); phone is the primary device, desktop merely supported. The shipped shell is a floating five-slot bar — Chat · Ringkasan · **+** · Kantong · Saya — where the centre button is manual entry. The chat is the exception: it drops the bar and carries a menu button in its header instead.

The product is called **lega**. The brand green is `#009A5B`, the
typeface Plus Jakarta Sans, and the mark a spirit level — see
`src/theme/theme-config.js`, which carries the whole palette. The repo
directory and the npm package are still `duit-akuh`/`lega` respectively;
nothing user-facing says "Duit Akuh" any more.

**The approved design boards are the specification.** Twenty artboards
cover every screen, down to the hex values and the nav's exact
measurements, and the shipped UI is built from them rather than from
MUI defaults. Building a surface "from memory" is how this went wrong
once already. The boards live in the canvas artifact; their vocabulary
is factored into `src/sections/common/board.jsx`, which is where a
screen's pieces come from.

The codebase started as the **Minimal UI v7.7.0 `starter-next-js`**
template (commercial MUI admin kit). Most of it has been replaced; what
remains of the starter is listed under "Known gaps".

## Domain invariants (from the PRD)

These are correctness rules, not preferences. Most of AC01–AC22 exist to catch violations of them.

- **Never use floating point for money.** Store integer rupiah or fixed-precision decimal (FR03).
- **Money must never be double-counted.** Transfers, top-ups and cash withdrawals are one atomic two-sided transaction and are _neither_ income nor expense; admin fees are a separate expense (FR02/AC02). Credit-card spending is an expense at purchase time and increases card debt — paying the bill reduces bank balance and debt but must **not** re-count the expense (AC03). Opening balance is not income (AC01).
- **Allocations are virtual, not assets.** Allocating to a goal never increases net assets; total active allocations on an account may not exceed its positive balance (FR07/AC05).
- **Credit limits are not money.** Available limit is never an asset nor "uang bebas pakai" (FR01/FR09).
- **Every write is idempotent.** Each posting carries a unique ID and an idempotency key; a confirmation submitted twice must produce exactly one transaction (FR03/AC04).
- **Confirm before every financial write**, showing the impact first; reads, filters and simulations need no confirmation (FR05). Ambiguous references (e.g. "BCA" matching two accounts) must be clarified, never guessed (AC04).
- **Nothing is deleted silently.** Corrections create a traceable revision/reversal plus an audit event with before/after versions (FR02/AC08).
- **Simulations never mutate real data** until the user explicitly applies the plan (FR11/AC07).
- **The LLM never computes money.** It proposes structured tool calls; the backend authorizes, validates and computes via tested functions. Receipt/statement content is data, never instructions (FR06 "Batas dan mekanisme AI").
- **Hard isolation per owner.** Every API enforces per-owner authorization; zero cross-account access is a release gate (AC08).
- **AI tools only draft or read — they never post.** Posting happens solely through the confirmation endpoint carrying an operation ID (FR05, §13).
- **Secrets never reach the client.** The PWA calls only our backend; the backend holds the LLM API key and Cloudflare Access tokens. A network inspection of the PWA must never reveal them (AC21).
- Never send full card numbers, PINs, bank OTPs or banking credentials to a model.

## AI service (PRD §13)

Self-hosted on the owner's own `lumi-ai` server, exposed via Cloudflare Tunnel. **No third-party AI provider** — user text, receipts and audio stay on that server, which is also the stated privacy guarantee.

| Function                        | Model                                  | Endpoint                                             | Auth                                              |
| ------------------------------- | -------------------------------------- | ---------------------------------------------------- | ------------------------------------------------- |
| Chat, tool calling, receipt OCR | `qwen3.5-9b` (vLLM, OpenAI-compatible) | `https://llm.lumicore.co.id/v1`                      | `Authorization: Bearer <key>`                     |
| Speech-to-text                  | WhisperX `large-v3`                    | `https://stt.lumicore.co.id/v1/audio/transcriptions` | `CF-Access-Client-Id` + `CF-Access-Client-Secret` |
| Fallback chat/vision            | `qwen2.5vl:7b`, `gemma4:12b` (Ollama)  | LAN `:11434`                                         | internal only                                     |

Both are OpenAI-compatible, so an OpenAI SDK pointed at these base URLs works. Build behind an adapter exposing `chat` / `vision` / `transcribe` so the backup or a cloud model can be swapped in; switching to cloud triggers a privacy notice.

Constraints that shape the design:

- **24,576 token context** (prompt + output) — summarize chat history, keep tool schemas terse, and remember one image eats a lot of it.
- **Max 1 image per request**, no video. Multi-photo receipts are processed one at a time and merged in the backend.
- **16 parallel requests** server-wide, shared with other apps — the backend needs a queue and per-user rate limiting.
- **Cloudflare: response must start within 100s** (else 524) and uploads cap at 100 MB. **Stream chat responses.** Voice messages cap at ~5 minutes.
- `chat_template_kwargs.enable_thinking=false` by default for transaction drafts and receipt extraction (faster); may be enabled for analysis and simulation explanations.
- `response_format: {"type":"json_object"}` is supported — use it for receipt extraction and drafts, with `temperature: 0`.
- Before sending a receipt photo: downscale to ~1600 px on the long edge, JPEG ~80%, and **strip EXIF/location**.
- `lumi-ai` is a dev box with no SLA or failover — a single point of failure. Every AI path needs a clear failure state with manual entry still working (AC09/AC22); at most one automatic retry, never an auto-post.
- The backend must log AI requests (owner, operation ID, kind, model, token usage, latency, status, tool calls) while keeping keys, card numbers, PINs and OTPs out of logs.

The MVP tool contract is tabulated in §13 (`get_accounts`, `get_balance`, `get_summary`, `find_transactions`, `run_simulation` need no confirmation; every `propose_*` does).

## Mobile/PWA requirements (PRD §12, FR16–FR18)

Mandatory for MVP, verified by AC15–AC18:

- Manifest, 192/512 + maskable icons, start URL, scope, `display: standalone`, HTTPS. Install prompt where available; iOS gets Share → Add to Home Screen guidance.
- **Service worker caches static shell assets only — never finance or chat APIs.** Offline must not fake success: drafts survive in-session marked unsaved, with no auto-post on reconnect.
- Single column, no horizontal page scroll at **320–430 CSS px**; portrait and landscape; respect notch/home-indicator safe areas.
- Composer stays above the keyboard without covering messages or confirmations; height follows the dynamic viewport; scroll position and drafts survive panel opens and backgrounding.
- Touch targets ≥ **44×44 CSS px**; body text and inputs ≥ **16 CSS px**; zoom not blocked.
- Lists render as cards, wide tables become stacked detail, long detail uses bottom sheets or full-screen panels.
- Charts must work via tap with labels and numeric summaries — never hover-only or color-only.
- Support screen readers, contrast and reduced motion.
- Chat shell targets **LCP ≤ 2.5s, CLS ≤ 0.1** on a documented 4G mobile profile (AI latency measured separately).

## Commands

```sh
npm run dev          # dev server on port 3033 (Turbopack)
npm run build        # production build
npm start            # serve production build on port 3033
npm run lint         # eslint over src/**/*.{js,jsx,ts,tsx}
npm run lint:fix     # eslint --fix
npm run fm:check     # prettier --check
npm run fm:fix       # prettier --write
npm run fix:all      # lint:fix + fm:fix
npm run clean        # rm -rf node_modules .next out dist build
```

The frontend has **no test runner** — no jest/vitest/playwright dependency
or test script exists, so verifying a React change means `npm run lint`,
`npm run build`, and looking at it. The backend has pytest; see below.

Requires Node >=22.12 (`engines`). `package-lock.json` and `yarn.lock` are both present; this project was installed with **npm** — stay on npm so the lockfiles don't diverge.

## Architecture

### Page shell → view separation

`src/app/**/page.jsx` files are deliberately thin: they export `metadata` and render a view component. All real UI lives in `src/sections/<feature>/`. Follow this split when adding pages.

```jsx
// src/app/(app)/target/page.jsx
export const metadata = { title: `Target - ${CONFIG.appName}` };
export default function Page() {
  return <TargetView />;
}
```

Route protection and chrome are applied in the segment `layout.jsx`, not
in pages: `src/app/(app)/layout.jsx` wraps the eight app surfaces in
`AuthGuard` + `AppShell`, and `src/app/auth/layout.jsx` wraps the five
auth screens in `GuestGuard` + a centred column. Both are one layout for
the whole segment on purpose — the guard used to be copied per page,
which is how a sixth screen could ship with none.

### Central config: `src/global-config.js`

`CONFIG` is the single switchboard for app name and auth.

- `CONFIG.auth.method` is `'session'` — our own email + password against
  the FastAPI backend (`src/auth/context/session/`). The template's
  `jwt`, `amplify`, `firebase`, `supabase` and `auth0` blocks are still
  in the file and configure nothing; no provider for them exists here.
- `CONFIG.auth.skip` is a template leftover that only the dead
  `/dashboard` segment reads. It does **not** bypass the real app's
  guard.

There is no `serverUrl` in play. The browser calls `/srv/*` on its own
origin and `next.config.mjs` rewrites that to `BACKEND_URL`; the
template's `src/lib/axios.js` is unused, because a Bearer-token instance
is the wrong shape for an httpOnly cookie.

### Theme pipeline

Styling is a layered MUI CSS-variables theme. Changes belong at the lowest layer that can express them:

1. `src/theme/theme-config.js` — **start here.** Palette, font families, border radius, default mode, CSS var prefix. Plain config object.
2. `src/theme/core/` — generated palette/typography/shadows/component overrides built from that config.
3. `src/theme/create-theme.js` — assembles `baseTheme`, then applies runtime settings.
4. `src/theme/with-settings/` — maps user settings (preset color, contrast, font size, RTL) onto the theme.
5. `src/theme/theme-overrides.js` — a ready-made example override (purple primary). Pass it as `themeOverrides` to `ThemeProvider` to apply; nothing imports it by default.

Because `cssVariables` is enabled, **read colors as `theme.vars.palette.*`, not `theme.palette.*`** — `theme.vars.*` emits the CSS variable and keeps light/dark switching working without a re-render. Channel variants (`grey['500Channel']`) exist for alpha compositing via `varAlpha` from `minimal-shared/utils`.

`src/global.css` handles font `@import`s and baseline resets only; it is imported once in `src/app/layout.jsx`.

### Settings persist via cookie, read on the server

`detectSettings()` (`src/components/settings/server.js`) reads the `app-settings` cookie in the root layout so theme mode and direction are correct on first paint. `defaultSettings` in `settings-config.js` carries `version: CONFIG.appVersion` — bumping the package version invalidates stored settings. `InitColorSchemeScript` in the root layout prevents dark-mode flash.

Guard anything cookie-based behind `CONFIG.isStaticExport`, as the root layout already does — `next/headers` is unavailable in static export.

### Forms: zod + react-hook-form via the `Field` namespace

Never hand-wire MUI inputs to react-hook-form. Use the wrappers:

```jsx
import { Form, Field, schemaUtils } from 'src/components/hook-form';

const Schema = z.object({ email: schemaUtils.email(), amount: z.number() });
const methods = useForm({ resolver: zodResolver(Schema), defaultValues });

<Form methods={methods} onSubmit={onSubmit}>
  <Field.Text name="email" label="Email" />
  <Field.DatePicker name="date" />
</Form>;
```

`Field` (`src/components/hook-form/fields.jsx`) is the full registry of
available inputs. `schemaUtils` provides shared zod validators.
`src/auth/view/session/sign-in-view.jsx` is the reference
implementation, and the auth screens wrap `Field` in their own
`AuthField` (`src/auth/components/auth-kit.jsx`) so all five look alike.

Not every form uses it. The money surfaces — manual entry, the
allocation sheet — are keypads and chips rather than labelled inputs,
because that is what the boards specify for a phone.

### Routing

All paths are centralized in `src/routes/paths.js` — add new routes there and reference `paths.*` rather than hardcoding strings. Navigate with the re-exported hooks from `src/routes/hooks` (not `next/navigation` directly) and link with `RouterLink` from `src/routes/components`.

`next.config.mjs` sets `trailingSlash: true`, so `/target` 308-redirects
to `/target/`. That also means every in-app link is a **full document
navigation**, not a client-side route change — worth knowing before
assuming state survives a tab tap.

Navigation is split by surface, on purpose.

Everywhere **except the chat**, it is `appTabs` in
`src/layouts/app/nav-config-app.jsx`: five slots, the middle one a
circular link to manual entry. `AppShell` decides, with one line —
`showTabs = pathname !== paths.chat`.

**The chat** drops the bar and renders `AppMenuButton`
(`src/layouts/app/app-menu.jsx`) in its header, driven by `appMenuTiles`.
It is the one surface with a composer, so it is the one place a floating
bar fights the keyboard for the bottom of the screen. Because the bar is
not there to fall back on, the menu holds **all eight** destinations at
the same depth rather than the bar's four — Budget, Target and Simulasi
are one tap from the chat, where from Ringkasan they are two.

Two consequences worth knowing. Sign-out is not in the menu: it lives in
Saya behind a confirmation dialog, and a second copy would be a second
thing to keep in step. And Budget is `solar:chart-square-outline`, in the
menu *and* on Ringkasan's own tiles, because Ringkasan owns `lega:chart`
in the tab bar and the two sat one above the other in the grid.

Safe areas follow the same split: `BoardBody` leaves the home indicator to
the tab bar's own margin, while the chat composer carries
`env(safe-area-inset-bottom)` itself — inside its padding, so the paper
runs to the screen edge instead of leaving a grey strip.

The template's `nav-config-dashboard.jsx`, `nav-config-account.jsx` and
`nav-config-workspace.jsx` drive the dead `/dashboard` segment only.

### Imports are lint-enforced in a non-obvious way

`perfectionist/sort-imports` runs at **error** severity with `type: 'line-length'` and a custom group order:

```
style → side-effect → types → builtin/external → @mui/* → src/routes/* →
src/hooks/* → src/utils/* → other src/* → src/components/* →
src/sections/* → src/auth/* → relative → object
```

Within each group, imports sort by **line length ascending**, with blank lines required between groups. Hand-written import blocks will almost always fail lint — run `npm run fix:all` after editing imports instead of ordering them manually.

Path alias: `src/...` resolves from the repo root via `jsconfig.json` `baseUrl: "."` (and the eslint alias resolver). This is a bare `src/` prefix, not `@/`.

### SVG imports

`@svgr/webpack` is wired for both bundlers in `next.config.mjs` — `*.svg` imports become React components. Note the config duplicates the rule for webpack and Turbopack; changes must be made in both places.

## Current state vs. the PRD

The MVP is largely built: a double-entry ledger, auth, the chat orchestrator with 13 tools, goals, budgets, simulations, CSV export, and a PWA shell wired to all of it. The root [`README.md`](README.md) has the setup and usage guide; the remaining gaps are listed below.

Stack decisions already made (2026-10-10):

- **Backend: FastAPI**, per the PRD's recommendation — a separate service in `backend/`. The ledger foundation exists; see `backend/README.md`.
- **Database: PostgreSQL locally, MySQL/MariaDB in production.** The PRD asks for PostgreSQL and it remains the better fit for this schema, but the cPanel host the app is deployed to has no PostgreSQL at all (`uapi Postgresql` answers "This server does not support this functionality"), only MariaDB 10.6. `backend/app/types.py` is what keeps the two equivalent — read it before touching a column type. The full suite passes on both.
- **Auth: own email + password**, Argon2id with server-side sessions in an httpOnly cookie and the §9 login throttle. Built; see `backend/README.md`.
- **AI: the self-hosted `lumi-ai` service** described above, behind a swappable adapter.

The PWA talks to the backend through a **same-origin proxy**: the browser
calls `/srv/*` and `next.config.mjs` rewrites it to FastAPI. That is not a
convenience — the session is an httpOnly `SameSite=Lax` cookie, which a
browser will not send cross-origin. Calling the backend directly would
mean `SameSite=None; Secure` or putting the token in JavaScript. Client
code lives in `src/lib/api.js`; there is no Bearer token anywhere.

The prefix is `/srv` and not the obvious `/api` because **content
blockers match on path**. An extension in the owner's Chrome killed
`fetch('/api/auth/me')`, `/api/accounts` and `/api/chat/messages` before
they left the browser — `TypeError: Failed to fetch`, nothing on the
wire — while `/api/summary` went through. Three places have to agree:
`BASE` in `src/lib/api.js`, the rewrite in `next.config.mjs`, and
`NEVER_CACHE_PREFIXES` in `public/sw.js`. Rewrites are baked at build
time, so changing it needs a rebuild in production.

Built so far — the chat-first shell:

- **Chat is the root route.** `src/app/(app)/` holds eight surfaces: `/`
  (chat), `/ringkasan`, `/data`, `/kantong`, `/budget`, `/target`,
  `/simulasi` and `/catat`, all inside `AppShell`. The old `/` →
  `/dashboard` redirect is gone.
- **`AppShell`** (`src/layouts/app/`) fills the dynamic viewport, scrolls
  only its content area, and compresses by the keyboard inset so the
  composer stays visible. `BottomTabs` hides while the keyboard is open.
- **Chat section** (`src/sections/chat/`): thread with
  sticky-bottom-only-when-already-at-bottom scrolling, composer whose
  draft survives navigation via `sessionStorage`, the board "Mulai"
  first-run state when no wallet exists yet, and the confirm flow
  below. Every bubble carries its own time, formatted by
  `src/utils/format-chat-time.js`, which is **pinned to Asia/Jakarta**
  rather than the device zone — the ledger's day boundaries are
  Jakarta's, and a bubble dated "besok" under a summary that counts it
  today is the app contradicting itself.
- **A pending draft opens in a sheet, not inline.** `DraftSheet`
  (`sections/chat/cards/`) owns the bottom of the screen, so the
  amount, the impact and the swipe are in view together and the editor
  has somewhere to open; the thread keeps only a stub that reopens it,
  because a confirmation must survive a stray swipe down without being
  decided by one. A *settled* draft is still the full `ActionCard`
  receipt in the thread. `DraftCard` branches per draft kind, because a
  goal, a budget and a reversal each need a different sentence beside
  the number.
- **Several entries from one sentence.** "Ngeluarin 150rb — obat 50,
  makan 70, minum 30" is three transactions and one *claim about them*.
  `propose_transactions` takes `stated_total` **separately from
  `transactions`**, and `app/domain/batch.py:reconcile` checks the
  parts against it; the stated total is never posted, which is the
  whole point — recorded alongside the parts it doubles the spending.
  More than one entry (or any `stated_total`) becomes one `batch`
  draft: one swipe, one `transactions.group_id`, all of it or none.
  Each entry still gets **its own** idempotency key
  (`<operation_id>:<index>`) — one shared key would make the second
  entry look like a replay of the first and drop it.
  In a batch an unresolvable wallet is left blank rather than raising,
  because erroring would throw away the entries the model read
  correctly; `_confirm_batch` then refuses the whole batch until every
  slot is filled (AC04 on the server, not just a disabled button), and
  the preview leaves unresolved entries out instead of inventing a row.
- **A read tool's result can be drawn, not just narrated.**
  `messages.view` (migration `e18a4b6c3d27`) holds `{kind, data}` taken
  straight from the tool output, so the card and the sentence above it
  cannot disagree and the model never restates a figure as a picture.
  `DRAWABLE_TOOLS` in the orchestrator is the whole registry — adding a
  card is one entry there plus a component. `SpendingCard` prints every
  number on its own bar and says "lewat budget" in words as well as
  amber, because FR18 forbids hover-only and colour-only charts; there
  is deliberately no chart library, since apexcharts is not installed
  and five labelled bars are five divs.
- **Named threads** (`app/services/chat/sessions.py`, migration
  `9a2e5d4c71b8`). `uq_conversation_per_user` is gone;
  `active_conversation()` is what replaces it — newest unarchived, else
  a new one — so FR14's "never have to choose a thread to begin" holds
  without a constraint. Threads are ordered by `max(messages.seq)`
  rather than a stored `last_message_at`: `seq` is already the ordering
  key, so there is no second value to drift. A thread is titled from
  its own first message, not by asking the model — a title is worth no
  round trip, and the sentence a person typed is what they will
  recognise. **There is no delete, deliberately:** archiving does the
  list's job, while deleting a thread would destroy the only record of
  *why* a transaction was entered, long after the transaction itself is
  immovable. Quoting across threads is refused for the same reason
  context is per thread (AC08 covers the rest).
- **Reply quotes a turn, and the model is told.** `messages.reply_to_id`
  (migration `3f1b7c0a94de`) is self-referential with `ON DELETE SET
  NULL` — losing the quoted turn must not take the reply with it — and
  `tests/conftest.py` nulls it before its bulk deletes for the same
  MySQL reason as `transactions.reverses_id`. The API validates the id
  against the sender before storing it and answers 404 otherwise (AC08),
  *before* the stream opens, because a 404 raised mid-generator reaches
  the client as a broken 200. `_as_prompt` prefixes the quoted text onto
  the user turn, capped at 160 characters: without it the model cannot
  tell which of ten earlier answers a short "yang itu" meant, and
  uncapped it would spend the 24,576-token window re-sending its own
  reply.
- **"Ubah dulu" revises a draft through the backend**, not by asking
  the model again: `POST /chat/drafts/{id}/revise` takes a field patch,
  re-validates it and recomputes the impact with the same functions
  that drew the first card. It returns a **different** draft — the old
  one is cancelled — so a confirmation already in flight cannot land on
  edited numbers. Only money kinds are revisable, and the allowlists in
  `app/services/chat/revise.py` and `cards/draft-revise.jsx` are two
  copies of one fact: the server's is the one that decides.
- **`src/sections/common/board.jsx`** is the shared vocabulary every
  surface is assembled from — hero cards, stat tiles, list rows, the
  progress ring, the wallet picker, the keypad. When a board changes,
  this file changes and the screens follow.
- **`SwipeConfirm`** (`src/components/swipe-confirm/`) is how a money
  write is committed: a deliberate drag, not a button next to the
  thumb. It stays a real `<button>`, so Enter works.
- **Five auth screens** under `src/app/auth/` — sign in, sign up, forgot
  password, check your mail, new password — on one `GuestGuard` layout.
- **PWA**: `src/app/manifest.js`, `public/sw.js`, `public/offline.html`,
  icons generated by `npm run gen:icons`.
- **`src/utils/format-money.js`** is the only place money becomes text,
  and it **throws on a non-integer amount** so a float cannot reach the
  user silently. The backend's `app/money.py:format_rupiah` is its
  counterpart for anything a server message has to say out loud.

Known gaps, in the PRD's own build order ("fondasi akun dan ledger → orkestrator chat → kendali chat semua modul → target dan kalkulator → visual, ekspor, QA"):

- **Deposit schedules.** Goals carry a target date but no deposit dates, so `remaining_deposits` is supplied by the caller rather than derived.
- **Benchmark runs are manual.** `backend/benchmarks/` measures the PRD's pilot gates against the real model; nothing runs it automatically.
- **Charts are not installed** — see the reference-template note below. Note the PRD forbids hover-only/color-only charts, so default chart configs need adapting.
- **The frontend has no test runner.** The backend has pytest covering AC01–AC05 and AC08; nothing covers the React side.
- **Physical device testing is not done** (AC15–AC18). The shell is built to the mobile mandate but has only been seen in a desktop browser at phone widths.
- **Install prompt UI is missing** (FR16 wants a button where available, plus iOS Share → Add to Home Screen guidance).
- **Voice and receipt photos are stage two.** The composer has both
  buttons and neither does anything yet; `/v1/audio/transcriptions` and
  the vision path are unwired.
- **Dead template routes.** `/dashboard/*` (six `BlankView` pages),
  `src/sections/blank/`, `src/layouts/dashboard/`,
  `src/layouts/auth-split/` and the three `nav-config-*` datasets are
  unreachable from the live app. Nothing is being cribbed from them any
  more, so they can go — along with `paths.dashboard.*` and the
  `CONFIG.auth.skip` branch that only they read.

Mobile mechanics worth knowing before touching the shell:

- The shell is `height: 100dvh` with `overflow: hidden`; **only the thread scrolls.** Any flex child that must shrink needs an explicit `minHeight: 0`, or the inner scroll area pushes the tabs off-screen.
- `useVirtualKeyboard()` (`src/hooks/`) reads `window.visualViewport` because `dvh` does not shrink for the keyboard on iOS Safari. Its open-threshold is 120px, not 0, so collapsing browser chrome is not mistaken for a keyboard.
- Safe areas come from `env(safe-area-inset-*)`, enabled by `viewportFit: 'cover'` in the root layout's `viewport` export. Do not add `maximumScale`/`userScalable` there — the PRD requires zoom to stay unblocked.
- **Icons must be registered** in `src/components/iconify/icon-sets.js` (224 are). An unregistered name is fetched at runtime, which flickers and breaks the offline shell — `Iconify` warns in the console when that happens.

## Backend (`backend/`)

A separate FastAPI service, on PostgreSQL locally and MariaDB in
production. Full detail in `backend/README.md`; the essentials:

```sh
cd backend
.venv/Scripts/python -m pytest                       # 394 tests
.venv/Scripts/python -m pytest -m "not integration"  # pure rules, no database
.venv/Scripts/python -m ruff check .
.venv/Scripts/alembic upgrade head
```

**The ledger is double-entry** — every transaction's entries sum to exactly
zero, debit positive and credit negative. Read `app/models.py`'s module
docstring before changing anything: that one property is what makes
transfers non-income (AC02), card payments non-double-counting (AC03), and
opening balances non-income (AC01). Do not add a code path that adjusts a
balance directly.

`app/domain/` is **pure** — no database, no framework. New money rules
belong there with a test, not in a service. `app/services/` owns
persistence, idempotency and ownership checks.

Money is integer rupiah (`BIGINT`) throughout; `app/money.py` rejects
non-integral floats rather than rounding (FR03).

**The schema has to run on two engines**, so every column type goes
through `app/types.py`. Do not reach for `sqlalchemy.dialects.postgresql`
in a model again — the four traps it exists to cover:

- `JSONB` does not exist on MariaDB (`JSON` there is a `LONGTEXT` alias
  with a `json_valid()` CHECK). Use `JsonDoc`, which keeps JSONB on
  PostgreSQL.
- **MariaDB has no timezone-aware timestamp.** `UtcDateTime` stores UTC
  and reattaches the offset on load; it also *refuses* a naive datetime
  rather than guessing. `app/db.py` pins `time_zone='+00:00'` per MySQL
  connection, because this host's system zone is WIB (+07) and a
  server-side `CURRENT_TIMESTAMP` default would otherwise be seven hours
  out. It pins `STRICT_ALL_TABLES` for the same class of reason: outside
  strict mode MySQL truncates an over-range amount with a warning.
- `sa.Uuid` renders native `uuid` on PostgreSQL and `CHAR(32)` elsewhere.
  `sa.UUID` does not — it emits a native type MariaDB only has from 10.7.
- **`Identity()` generates nothing on MySQL.** `messages.seq` therefore
  gets an explicit `AUTO_INCREMENT`, applied twice on purpose: a
  `after_create` DDL listener in `app/models.py` for
  `metadata.create_all()` (how the tests build the schema) and an
  `op.execute` in the migration (`op.create_table` does not fire DDL
  events). Without it every message insert fails with "Field 'seq'
  doesn't have a default value".

Two behaviour differences the tests encode rather than paper over: a
CHECK violation is an `IntegrityError` on PostgreSQL but an
`OperationalError` (error 4025) on MySQL, and a bulk `DELETE` over a
table with a self-referencing `RESTRICT` foreign key succeeds on
PostgreSQL while MySQL checks row-by-row and aborts — which is why
`tests/conftest.py`'s `reset_tables` nulls `transactions.reverses_id` and
`accounts.linked_account_id` first.

**Authentication** is email + password with server-side sessions in an
httpOnly cookie (Argon2id, token stored only as a hash). `deps.get_current_user`
is the only gate and has no development bypass. One trap it already hit: a
control that must persist across a _failed_ request — the login throttle —
needs an explicit commit before raising, or `get_db`'s rollback silently
discards it.

Environment comes from `backend/.env` (gitignored). `backend/setup-db.sql`
is generated per machine, contains the dev role's password, and is also
gitignored — recreate it rather than looking for it in git.

## Deployment (cPanel, Jagoan Hosting)

Production is the shared cPanel account `rswicent` on
`heroic.jagoanhosting.id` (SSH on port **45022**, publickey only). That
account also hosts an unrelated Laravel project on the main domain —
`public_html -> /home/rswicent/rswicentral.my.id/current/public`. **Do not
touch the main domain.**

| | frontend | backend |
| --- | --- | --- |
| domain | `finance.rswicentral.my.id` | `api-finance.rswicentral.my.id` |
| app root | `~/finance.rswicentral.my.id/app` | `~/api-finance.rswicentral.my.id/app` |
| runtime | Node **20.20.2** (Passenger) | Python **3.11.17** (Passenger) |
| entry | `server.js` (Next standalone) | `passenger_wsgi.py` |

**Each deployment directory is named after the domain it serves**, so the
GitHub variables `WEB_HOST` and `API_HOST` are the only configuration: one
value is both the path under `$HOME` and the host the smoke test probes.
The activate scripts take it as their second argument and hardcode no
paths. `agann.my.id` was abandoned (see below), so these subdomains are
the permanent home, not a staging step.

`npm run build` is not enough for this host: set `BUILD_STANDALONE=1` so
Next emits `server.js` plus a pruned `node_modules`, because the server has
no build toolchain. The bundle **must be built on Linux** — a Windows build
ships `@next/swc-win32-*` binaries that cannot load there. CI does this.

Constraints that shaped the deploy scripts, all verified on the box:

- **No `rsync`** — artifacts move as `tar` + `scp`.
- **Node caps at 20.20.2**, below `package.json`'s `engines` (>=22.12), so
  CI installs with `--engine-strict=false`.
- **Passenger's app root is fixed.** The CloudLinux selector resolves
  symlinks when it writes the `.htaccess` block, so a
  `current -> releases/rX` symlink bakes the release name into the config
  (and into the venv path). Releases are swapped by *moving directories*
  (`app` ⇄ `app.old`) instead, which keeps the registration and the
  virtualenv stable. Restart is `touch app/tmp/restart.txt`.
- **`.htaccess` is not part of the build.** It carries the Passenger
  directives, so `shared/htaccess` holds the canonical copy and each
  activate script copies it into the new release's `public/`.
- **Secrets live only in `shared/.env`** (mode 600, outside every release,
  never rewritten by a deploy). The LLM key and Cloudflare Access tokens
  are there and nowhere else — not in GitHub (AC21).
- **The app root must be traversable by LiteSpeed (0755).** `tar` records
  the mode of the directory the archive was built from, and `mktemp -d` is
  0700, so an unpacked release inherits 0700 — which LiteSpeed answers
  with a bare 404, no log line, no hint. The activate scripts normalise
  directory modes after unpacking.
- **The ASGI bridge must be built lazily, inside `application()`.** Python
  apps run under LiteSpeed's `lswsgi`, which imports the module in a
  master process and then forks workers. `a2wsgi` starts an event loop on
  a background thread when constructed, and threads do not survive
  `fork()`, so a bridge built at import time makes every request hang
  until the gateway gives up — with nothing in `stderr.log`. See
  `deploy/passenger_wsgi.py`.
- **A smoke test cannot just check for HTTP 200.** The public edge answers
  non-browser clients with an Imunify360 "One moment, please..."
  interstitial that *is* a 200, so the scripts match on body content —
  `"status":"ok"` for the API, a `/_next/` asset for the web app. They run
  from the server over plain DNS; see "Verifying a deploy" below for the
  loopback trap that makes any other probe lie.

```sh
# deploy: push to main, or Actions -> "Deploy ke cPanel" -> Run workflow
ssh duitakuh 'bash -s' -- api < deploy/rollback.sh   # instant app <-> app.old swap
ssh duitakuh 'bash -s' -- web < deploy/rollback.sh
```

Rollback does **not** revert migrations, by design.

### Verifying a deploy

Both subdomains are live and served by Passenger. Two things make this
host easy to misdiagnose, and between them they once produced a thoroughly
convincing false negative:

- **The box does not listen on 127.0.0.1.** It answers on `101.50.1.81`,
  so `curl --resolve host:443:127.0.0.1` lands on a default vhost and
  returns `/cgi-sys/defaultwebpage.cgi` no matter how healthy the app is.
  Never use a loopback probe here.
- **The Imunify360 edge answers non-browser clients** with a "One moment,
  please..." interstitial that is *itself* HTTP 200, so a status-code
  check passes against a dead app. Requests made *from the server* skip
  the interstitial.

So: probe from the server over ordinary DNS, and match on the body, which
is what the activate scripts do.

```sh
ssh duitakuh 'curl -sS https://api-finance.rswicentral.my.id/health'   # {"status":"ok",...}
ssh duitakuh 'curl -sS https://finance.rswicentral.my.id/ | head'      # must contain /_next/
```

`~/<domain>/app/stderr.log` is where Passenger writes a failed boot.

`agann.my.id` was dropped deliberately (2026-10-10). It is registered to a
different cPanel account on this server, so cPanel refused the subdomains
outright ("you can not add a DNS record for a subdomain of another user's
domain"), and its apex points at Vercel. Nothing in the repo should refer
to it.

## Reference template (`_reference/`, gitignored)

`_reference/Minimal_JavaScript_v7.7.0/` holds the unmodified vendor package. **`next-js/` is the full demo** and is the place to copy proven implementations from — it shares this exact architecture, so components usually drop in with only import-path fixes.

Most relevant to this project:

- `next-js/src/sections/overview/banking/` — balance statistics, expense categories, recent transactions. Closest existing match to the PRD's domain.
- `next-js/src/sections/invoice/` — list/detail/create with totals and line items.
- `next-js/src/sections/overview/analytics/` — chart-heavy dashboard widgets.

Two gaps to know when copying:

- **Charts are not installed.** Demo widgets depend on `apexcharts` + `react-apexcharts` and `src/components/chart/` (absent from the starter). Install both and copy the `chart` component folder before porting any chart widget.
- The demo also has `src/actions/` (SWR data fetchers) and `src/locales/` (i18n), neither of which exists here.

`src/_mock/` **is** present in the starter and is the fixture source the demo sections expect.
