# Recurring-issue lint/review gates

Two categories kept reappearing cycle-over-cycle in the code-quality scans. Task
L6 added automated gates so new code can't silently reintroduce them.

## Gate 1 — Frontend data-fetch bypass (ESLint, blocking)

**Where:** `eslint.config.mjs`, a scoped `no-restricted-syntax` block.

Components / pages / hooks / utils must route backend calls through
`services/apiService` (`authenticatedGet/Post/Put/Delete`) and must not:

- call `fetch(...)` directly, or
- hand-build a base URL from `import.meta.env.VITE_API_URL`.

**Scope / exemptions (precise, zero false positives on the current tree):**

- Rule applies ONLY to `src/{components,pages,hooks,utils}/**`.
- The `services/` and `config/` layer is **not** in the rule's `files`, so it stays
  exempt — it legitimately owns the one real `fetch` / base-URL construction.
- Test files (`*.test.*`, `*.spec.*`, `__tests__/`), mocks (`__mocks__/`), and
  `components/examples/**` are excluded.
- `pages/public/PublicLandingPage.tsx` is excluded: its single `fetch` reads a
  CloudFront static asset (`landing.json`), not an API call.

**Runs as part of** `npm run lint` (it is `eslint src`). Passes clean today;
fires with an informative message on any new bypass.

## Gate 2 — Tables without a responsive wrapper (script, advisory)

**Where:** `scripts/check-table-wrappers.js`, exposed as `npm run lint:tables`.

Flags any Chakra `<Table>` not inside a `<TableContainer>` / an element with
`overflowX` / a `useBreakpointValue` card fallback. A precise JSX-ancestor check
is a custom-ESLint-rule's worth of work; a bounded text scan (6-line look-back,
skipping tests/mocks/examples and lowercase `<table>`) is reliable and cheap.

**Why advisory (not wired into the blocking `lint` chain yet):** the check
surfaces 6 genuinely-unwrapped tables that pre-date L6 and are outside its scope
(M6/L1 only wrapped a specific set). Blocking `npm run lint` on them would fail
the current codebase. Wrap these, then promote `lint:tables` into the `lint`
chain / pre-commit / CI:

- `components/TenantAdmin/ParameterManagement.tsx:330`
- `components/TenantAdmin/StorageTab.tsx:94`, `:157`
- `components/reports/AangifteIbReport.tsx:320`
- `components/reports/BnbReturningGuestsReport.tsx:201`
- `pages/ZZPDebtors.tsx:198` (nested expansion table)

Run it any time with `npm run lint:tables` (exit 1 when offenders exist).
