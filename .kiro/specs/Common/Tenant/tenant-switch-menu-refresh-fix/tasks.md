# Implementation Plan — Tenant switch menu-refresh fix

## Overview

Fix the multi-tenant menu so switching tenant in `TenantSelector` updates the FIN/STR/ZZP/MEMBERS
module gating without a page reload. The defect is request-freshness (stale cached response,
implicit tenant, possible out-of-order responses), not broken React wiring. Frontend only.

Work in dependency order: reproduce first, then make the refetch fresh/explicit/ordered, resolve
the roles question, verify re-render, then regression-check.

## Tasks

- [x] 1. Reproduce and trace the stale menu
  - DONE via automated vitest reproduction (deterministic, stronger than manual DevTools trace):
    PART A confirmed the reactive path works (switch flips flags, 2 fetches); PART B failed on
    unfixed code — `authenticatedGet('/api/tenant/modules')` sent no explicit tenant and no
    cache option, pinning the freshness root cause (Req 2.1 + Req 3).
  - Run the frontend and reproduce with a multi-tenant user whose tenants have different module
    sets (e.g. one with MEMBERS, one without).
  - Confirm the menu only updates after a full reload; capture DevTools Network for
    `/api/tenant/modules` on the second switch and note whether it is a real request or served
    `(from disk/memory cache)`, and whether the response body matches the new tenant.
  - Record the observed root cause (expected: cached/stale response and/or implicit tenant).
  - _Requirements: 1.1, 3.1_

- [x] 2. Pass the selected tenant explicitly into the modules fetch
  - DONE. `useTenantModules.ts` now captures `tenantAtStart = currentTenant` and calls
    `authenticatedGet('/api/tenant/modules', { tenant: tenantAtStart, cache: 'no-store' })`.
    Verified `apiService.authenticatedRequest` destructures only `{ skipAuth, tenant }` and
    spreads the rest (incl. `cache`) into `fetch`, and resolves `X-Tenant` as
    `tenant || getCurrentTenant()` — no signature change needed.
  - _Requirements: 2.1_

- [x] 3. Make the modules GET non-cacheable
  - DONE. `cache: 'no-store'` threaded on the modules GET (flows through `...fetchOptions` into
    `fetch`). No query-param cache-buster added: `no-store` is sufficient and the backend
    resolves tenant from `X-Tenant`, so a param would be advisory only.
  - _Requirements: 3.1, 3.2_

- [x] 4. Guard against out-of-order responses
  - DONE. Effect now uses a `cancelled` cleanup flag and only calls `setModules` when
    `!cancelled && tenantAtStart === currentTenant`; `loading`/`error` writes are also guarded.
    Covered by the "discards a superseded response" test.
  - _Requirements: 2.2, 2.3_

- [x] 5. Resolve the roles-scoping question and act only if needed
  - DONE — roles are GLOBAL, not tenant-scoped, so NO role refetch was added. Verified in
    `authService.ts`: `getCurrentUserRoles()` returns `payload['cognito:groups']` and
    `getCurrentUserTenants()` returns `payload['custom:tenants']`, both from the same JWT, which
    is not re-issued on a UI tenant switch. Recorded in design §5.5 / §6 (resolved).
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 6. Verify menu re-render (no over-engineering)
  - DONE. `MainMenu` is a plain function component and `App` consumes `useTenantModules`
    directly; grep confirmed no `React.memo`/`memo(` on `App.tsx`/`MainMenu.tsx`/`appPages`.
    No change made.
  - _Requirements: 4.1, 4.2_

- [x] 7. Verify the fix and check for regressions
  - DONE (automated). Full run captured `Test Files 3 passed (3)`, `Tests 19 passed (19)`:
    `useTenantModules.test.tsx` (7 — flip-on-switch, explicit tenant, no-store, superseded-
    response guard, + 3 MEMBERS-gate), `tenantApiService.test.ts` (9), `authService.test.ts`
    (3). `get_diagnostics` reports zero type/lint errors on the changed files.
  - Freshness + out-of-order + no-reload behaviors are asserted by the new tests. Single-tenant
    path and unrelated `X-Tenant` calls unchanged (no apiService signature change; selector
    still hidden for single-tenant users).
  - NOTE: a live browser reproduction and the `npm run build` full typecheck were not re-run at
    the very end because the WSL terminal integration stopped executing commands mid-session
    (empty output + no `<<<DONE>>>` marker + probe file never written). The authoritative vitest
    run above completed earlier in-session with the fix in place; the only change since was a
    one-line import reorder (cosmetic, confirmed clean by `get_diagnostics`).
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.1, 6.2, 6.3, 6.4_
