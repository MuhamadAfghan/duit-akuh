# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Web pencatatan keuangan pribadi berbasis AI, for Indonesian users (IDR, Bahasa Indonesia, Asia/Jakarta).

Requirements: **`docs/PRD.md` (v1.3) is the source of truth.** It defines FR01–FR18 and AC01–AC22 — cite those IDs when implementing or testing. The `PRD_Keuangan_AI_Web_v1.docx` still at the repo root is the superseded **v1.1** and should not be read; v1.3 adds the AI service spec (section 13) and the PWA/mobile mandate (section 12).

**The product is chat-first and mobile-first.** One persistent conversation is the main surface and must be able to start _and finish_ every feature in a release (FR14). The dashboard is a companion view over the same data, not the primary UI. A mobile-first **PWA is mandatory for MVP** (FR16) with bottom tabs Chat / Ringkasan / Data; phone is the primary device, desktop merely supported. The current codebase reflects none of this yet — see "Current state vs. the PRD".

The codebase is the **Minimal UI v7.7.0 `starter-next-js`** template (commercial MUI admin kit), copied to the repo root and renamed to `duit-akuh` (the PRD leaves the product name undecided). It is a starter: the dashboard pages are intentionally blank placeholders (`BlankView`) waiting to be replaced with real features.

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

There is **no test runner configured** — no jest/vitest/playwright dependency or test script exists. If tests are needed, the harness has to be added first.

Requires Node >=22.12 (`engines`). `package-lock.json` and `yarn.lock` are both present; this project was installed with **npm** — stay on npm so the lockfiles don't diverge.

## Architecture

### Page shell → view separation

`src/app/**/page.jsx` files are deliberately thin: they export `metadata` and render a view component. All real UI lives in `src/sections/<feature>/`. Follow this split when adding pages.

```jsx
// src/app/dashboard/page.jsx
export const metadata = { title: `Dashboard - ${CONFIG.appName}` };
export default function Page() {
  return <BlankView title="Page one" />;
}
```

Route protection and chrome are applied in the segment `layout.jsx`, not in pages — `src/app/dashboard/layout.jsx` wraps children in `AuthGuard` + `DashboardLayout`, auth pages wrap in `GuestGuard` + `AuthSplitLayout`.

### Central config: `src/global-config.js`

`CONFIG` is the single switchboard for app name, server URL, and auth. Two fields change app-wide behavior:

- `CONFIG.auth.method` — `'jwt' | 'amplify' | 'firebase' | 'supabase' | 'auth0'`. `AuthGuard` picks its sign-in redirect from this. Only the **jwt** provider is actually implemented in this starter (`src/auth/context/jwt/`); the other paths exist in `src/routes/paths.js` but have no view or provider here.
- `CONFIG.auth.skip` — when `true`, `src/app/dashboard/layout.jsx` renders the dashboard without `AuthGuard`. Use this to work on UI without a backend.

`CONFIG.serverUrl` comes from `NEXT_PUBLIC_SERVER_URL` in `.env`, which **still points at the vendor's demo API** (`api-dev-minimal-v700.pages.dev`). Auth calls (`/api/auth/me`, `/api/auth/sign-in`) go there via `src/lib/axios.js`. Replace this with the real backend before building features that persist data.

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

`Field` (`src/components/hook-form/fields.jsx`) is the full registry of available inputs. `schemaUtils` provides shared zod validators. `src/auth/view/jwt/jwt-sign-in-view.jsx` is the reference implementation.

### Routing

All paths are centralized in `src/routes/paths.js` — add new routes there and reference `paths.*` rather than hardcoding strings. Navigate with the re-exported hooks from `src/routes/hooks` (not `next/navigation` directly) and link with `RouterLink` from `src/routes/components`.

`next.config.mjs` sets `trailingSlash: true`, so `/dashboard` 308-redirects to `/dashboard/`.

Sidebar navigation is data-driven: edit the `navData` array in `src/layouts/nav-config-dashboard.jsx` (supports `subheader` groups and nested `children`). The account menu and workspace switcher are separate datasets — `_account` in `nav-config-account.jsx` and `_workspaces` in `nav-config-workspace.jsx`. Nav icons resolve from `public/assets/icons/navbar/*.svg` (27 available) through the local `icon()` helper.

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

The repo is currently **frontend scaffolding only** — a themed Next.js shell. Nothing in the PRD's domain is implemented yet.

Stack decisions already made (2026-10-10):

- **Backend: FastAPI + PostgreSQL**, per the PRD's recommendation — a separate service in `backend/`. The ledger foundation exists; see `backend/README.md`.
- **Auth: own email + password** (needs argon2/bcrypt hashing plus login attempt rate limiting per §9). The template's sign-in/sign-up views exist and can be reused.
- **AI: the self-hosted `lumi-ai` service** described above, behind a swappable adapter.

The PWA talks to the backend through a **same-origin proxy**: the browser
calls `/api/*` and `next.config.mjs` rewrites it to FastAPI. That is not a
convenience — the session is an httpOnly `SameSite=Lax` cookie, which a
browser will not send cross-origin. Calling the backend directly would
mean `SameSite=None; Secure` or putting the token in JavaScript. Client
code lives in `src/lib/api.js`; there is no Bearer token anywhere.

Built so far — the chat-first shell:

- **Chat is the root route.** `src/app/(app)/` holds the three surfaces: `/` (chat), `/ringkasan`, `/data`, inside `AppShell`. The old `/` → `/dashboard` redirect is gone.
- **`AppShell`** (`src/layouts/app/`) fills the dynamic viewport, scrolls only its content area, and compresses by the keyboard inset so the composer stays visible. `BottomTabs` hides while the keyboard is open.
- **Chat section** (`src/sections/chat/`): thread with sticky-bottom-only-when-already-at-bottom scrolling, composer whose draft survives navigation via `sessionStorage`, and the in-chat `ActionCard` → `TransactionDraftCard` confirm flow.
- **PWA**: `src/app/manifest.js`, `public/sw.js`, `public/offline.html`, icons generated by `npm run gen:icons`.
- **`src/utils/format-money.js`** is the only place money becomes text, and it **throws on a non-integer amount** so a float cannot reach the user silently.

Known gaps, in the PRD's own build order ("fondasi akun dan ledger → orkestrator chat → kendali chat semua modul → target dan kalkulator → visual, ekspor, QA"):

- **The frontend still talks to nothing.** The ledger exists in `backend/`, but the Next.js app has no client for it — the chat remains stubbed.
- **Goals, budgets and simulation** have tables and rules but no services, so their tools are withheld from the model.
- **No AI adapter.** Nothing calls `lumi-ai` yet.
- **Chat is not streamed to the browser.** The backend adapter streams from vLLM (required: Cloudflare 524s past 100s), but `/chat/messages` returns one complete turn.
- **Charts are not installed** — see the reference-template note below. Note the PRD forbids hover-only/color-only charts, so default chart configs need adapting.
- **The frontend has no test runner.** The backend has pytest covering AC01–AC05 and AC08; nothing covers the React side.
- **The chat thread does not survive navigation.** `ChatView` holds messages in local `useState`, so switching to Ringkasan and back empties the conversation. The PRD wants one thread that continues across sessions and devices (FR15), which only the backend can provide — do not paper over this with client storage; it is the orchestrator's job.
- **Install prompt UI is missing** (FR16 wants a button where available, plus iOS Share → Add to Home Screen guidance).
- **`/dashboard/*` still exists** from the template. It is dead weight under the new IA and should be deleted once nothing is being cribbed from it.
- `src/sections/blank/` is likewise leftover template scaffolding.

Mobile mechanics worth knowing before touching the shell:

- The shell is `height: 100dvh` with `overflow: hidden`; **only the thread scrolls.** Any flex child that must shrink needs an explicit `minHeight: 0`, or the inner scroll area pushes the tabs off-screen.
- `useVirtualKeyboard()` (`src/hooks/`) reads `window.visualViewport` because `dvh` does not shrink for the keyboard on iOS Safari. Its open-threshold is 120px, not 0, so collapsing browser chrome is not mistaken for a keyboard.
- Safe areas come from `env(safe-area-inset-*)`, enabled by `viewportFit: 'cover'` in the root layout's `viewport` export. Do not add `maximumScale`/`userScalable` there — the PRD requires zoom to stay unblocked.
- **Icons must be registered** in `src/components/iconify/icon-sets.js` (224 are). An unregistered name is fetched at runtime, which flickers and breaks the offline shell — `Iconify` warns in the console when that happens.

## Backend (`backend/`)

A separate FastAPI + PostgreSQL service. Full detail in `backend/README.md`;
the essentials:

```sh
cd backend
.venv/Scripts/python -m pytest                       # 58 tests
.venv/Scripts/python -m pytest -m "not integration"  # 38, no database needed
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

**Authentication** is email + password with server-side sessions in an
httpOnly cookie (Argon2id, token stored only as a hash). `deps.get_current_user`
is the only gate and has no development bypass. One trap it already hit: a
control that must persist across a _failed_ request — the login throttle —
needs an explicit commit before raising, or `get_db`'s rollback silently
discards it.

Environment comes from `backend/.env` (gitignored). `backend/setup-db.sql`
is generated per machine, contains the dev role's password, and is also
gitignored — recreate it rather than looking for it in git.

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
