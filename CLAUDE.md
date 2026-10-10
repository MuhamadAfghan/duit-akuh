# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Web pencatatan keuangan pribadi berbasis AI, for Indonesian users (IDR, Bahasa Indonesia, Asia/Jakarta).

Requirements: `PRD_Keuangan_AI_Web_v1.docx` (v1.1) at the repo root is the source of truth; **`docs/PRD.md` is a readable/greppable text mirror of it** — read the mirror, and re-generate it if the .docx changes. The PRD defines FR01–FR15 and AC01–AC14; cite those IDs when implementing or testing.

**The product is chat-first.** One persistent conversation is the main surface and must be able to start _and finish_ every feature in a release (FR14). The dashboard is a companion view over the same data, not the primary UI. The current codebase does not reflect this yet — see "Current state vs. the PRD".

The codebase is the **Minimal UI v7.7.0 `starter-next-js`** template (commercial MUI admin kit), copied to the repo root and renamed to `duit-akuh` (the PRD leaves the product name undecided). It is a starter: the dashboard pages are intentionally blank placeholders (`BlankView`) waiting to be replaced with real features.

## Domain invariants (from the PRD)

These are correctness rules, not preferences. Most of AC01–AC14 exist to catch violations of them.

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
- Never send full card numbers, PINs, bank OTPs or banking credentials to a model.

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

The repo is currently **frontend scaffolding only**. Nothing in the PRD's domain is implemented yet. Known gaps, in the PRD's own suggested build order ("fondasi akun dan ledger → orkestrator chat → kendali chat semua modul → target dan kalkulator → visual, ekspor, QA"):

- **No backend, no database, no ledger.** The PRD suggests Next.js + FastAPI + PostgreSQL + Docker Compose but explicitly leaves the framework decision open. Nothing has been chosen or built.
- **No chat surface.** `/` currently redirects to `/dashboard`, and the dashboard is the only layout. A chat-first app needs chat as the default route and mobile tab.
- **Auth points at the vendor demo API** (see `CONFIG` below) and must be replaced before any real data exists.
- **No AI provider.** The PRD requires an adapter layer so the provider can be swapped; nothing is wired.
- **Charts are not installed** — see the reference-template note below.
- **No test runner**, while AC01–AC14 are concrete, checkable scenarios that want automated coverage. The ledger invariants above are exactly the kind of logic that needs tests before features pile on top.

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
