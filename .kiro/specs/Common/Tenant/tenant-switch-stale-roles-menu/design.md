# Tenant Switch Stale Roles Menu Bugfix Design

## Overview

When a user switches the active tenant via the `TenantSelector` dropdown without a page
reload, `MainMenu` keeps gating entries on the roles resolved at login/mount instead of the
newly selected tenant's effective (merged global + per-tenant) roles. The result: entries
gated on a role the user does not hold for the new tenant stay visible (e.g. `Tenantbeheer`
on `h-dcn`, which yields a backend 403 when clicked), and entries for tenant-scoped roles the
user DOES hold on the new tenant are missing (e.g. `Leden Overzicht`).

The root cause is verified and narrow: the fetch primitive already exists —
`getCurrentUserRoles()` in `frontend/src/services/authService.ts` already calls
`GET /api/auth/me` with the `X-Tenant` header and falls back to JWT `cognito:groups` on
failure — but `AuthContext` (`frontend/src/context/AuthContext.tsx`) only resolves
`user.roles` on mount/login through `checkAuthState()`. `refreshUserRoles()` just re-runs
`checkAuthState()` and is only called on login. Nothing re-resolves roles when
`currentTenant` changes in `TenantContext` (`frontend/src/context/TenantContext.tsx`). A full
page reload masks the bug because mount re-runs `checkAuthState()` against the persisted
tenant.

The fix adds a tenant-keyed role re-resolution on switch, mirroring the exact effect pattern
already shipped for module flags in `frontend/src/hooks/useTenantModules.ts` (tenant captured
at effect start, tenant passed explicitly, `cache: 'no-store'`, cancelled-flag +
tenant-at-start out-of-order guard). Scope is **frontend only**: `GET /api/auth/me` already
returns tenant-merged roles and already guarantees `SysAdmin` globally, so no backend change
is required.

## Glossary

- **Bug_Condition (C)**: An in-app tenant switch (no reload) where the newly selected
  tenant's effective role set differs from the currently held `user.roles`.
- **Property (P)**: After the switch, `user.roles` equals the active tenant's effective
  (merged global + per-tenant) roles, and the menu is gated accordingly.
- **Preservation**: Login/mount role resolution, single-tenant behavior, module-flag
  freshness, `localStorage` persistence, and the App-level module-loss redirect all remain
  unchanged.
- **Effective roles**: The authoritative role set returned by `GET /api/auth/me` for a given
  `X-Tenant` — the global JWT `cognito:groups` merged with the per-tenant rows from
  `user_tenant_roles`.
- **`getCurrentUserRoles()`**: Function in `frontend/src/services/authService.ts` that calls
  `GET /api/auth/me` with `X-Tenant` (read today from `localStorage.selectedTenant`) and falls
  back to JWT `cognito:groups` on failure.
- **`checkAuthState()`**: Internal `AuthContext` routine that resolves the full user object
  (email, name, roles, tenants) on mount/login.
- **`currentTenant`**: The active tenant held in `TenantContext`; the trigger for
  re-resolution.
- **`refreshRolesForTenant(tenant)`**: New `AuthContext` action introduced by this fix that
  re-resolves only `user.roles` for an explicitly supplied tenant.

## Bug Details

### Bug Condition

The bug manifests when the user switches the active tenant through the `TenantSelector`
dropdown without reloading the page, and the newly selected tenant's effective role set
differs from the role set currently in `AuthContext.user.roles`. `AuthContext` never
re-resolves roles on that trigger — `refreshUserRoles()` is wired only to login, and
`TenantContext` only updates `currentTenant`/`localStorage`. So `MainMenu`, which gates every
entry on a compound `module flag AND user.roles` check, evaluates against the previous
tenant's roles.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type TenantSwitchEvent {
           fromTenant, toTenant, globalRoles,
           effectiveRolesForToTenant, reloaded
         }
  OUTPUT: boolean

  RETURN input.reloaded = FALSE
         AND input.effectiveRolesForToTenant <> currentUserRoles()
END FUNCTION
```

### Examples

- User `peter@pgeers.nl` holds global roles `Tenant_Admin`, `SysAdmin`, `ZZP_CRUD`,
  `Finance_CRUD`, `STR_CRUD`. Switching to `h-dcn` (no reload) — **expected:** `Tenantbeheer`
  hidden (no `Tenant_Admin` on `h-dcn`); **actual:** `Tenantbeheer` still shown, click → 403.
- Same user on `h-dcn` holds a tenant-scoped Members role not in the JWT — **expected:**
  `Leden Overzicht` shown; **actual:** missing until reload.
- `Systeembeheer` (`SysAdmin`) — **expected:** stays visible on every tenant (SysAdmin is the
  single global exception); **actual (today):** correct only because roles are stale; must
  stay correct after the fix re-resolves roles.
- Rapid switch A → B → C — **expected:** menu reflects C; **actual risk without a guard:** a
  late response for A or B overwrites C's roles.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Login/mount role resolution via `checkAuthState()` is untouched (initial `user.roles` still
  populated exactly as today).
- Single-tenant users see no behavioral change — with one tenant there is no switch trigger.
- Module-flag freshness from `useTenantModules` / `useTenantFunctions`
  (`hasFIN`, `hasSTR`, `hasZZP`, `hasMEMBERS`, `hasFunction`) and the compound
  module-flag-AND-role gating in `MainMenu` remain as-is.
- `TenantContext` continues to persist the selection to `localStorage` and update
  `currentTenant` exactly as today.
- The App-level module-loss redirect effect in `frontend/src/App.tsx` behaves as today.

**Scope:**
All inputs that do NOT involve an in-app tenant switch that changes the effective role set are
completely unaffected. This includes:
- Single-tenant sessions (no switch possible).
- The login/mount path (roles resolved once, as today).
- Switches between tenants whose effective role set is identical (no visible change; no
  flicker that removes a still-valid entry).

_Note:_ The expected correct behavior on a switch is defined in Correctness Properties
(Property 1). This section captures what must NOT change.

## Hypothesized Root Cause

Root cause is verified (not merely hypothesized) from reading the in-scope code:

1. **No tenant-keyed role refresh (primary)**: `AuthContext` resolves `user.roles` only in
   `checkAuthState()`, called from a mount-only `useEffect([])` and from `refreshUserRoles()`
   (login only). There is no effect keyed on `currentTenant`, so a switch never re-fetches
   roles.

2. **Wrong assumption in the related spec**: `tenant-switch-menu-refresh-fix` refreshed module
   flags but concluded "roles are global, no role refetch needed." Roles are in fact
   tenant-scoped (only `SysAdmin` is global), which is precisely the gap this fix closes.

3. **Compound gating amplifies the staleness**: `MainMenu` gates on `module flag AND
   user.roles`. Module flags already refresh on switch, but stale `user.roles` still both
   over-shows (403-yielding entries) and under-shows (missing tenant-scoped entries).

4. **Freshness risk on the fetch itself**: `getCurrentUserRoles()` reads the tenant from
   `localStorage` and does not set `cache: 'no-store'`. Since the `/api/auth/me` URL is
   identical across tenants, a naive re-resolution could read a lagging tenant or replay a
   cached body — the same hazards `useTenantModules` already defends against.

## Correctness Properties

Property 1: Bug Condition - Roles Re-resolved For Active Tenant On Switch

_For any_ input where the bug condition holds (`isBugCondition` returns true — an in-app
tenant switch with no reload that changes the effective role set), the fixed code SHALL
re-resolve `user.roles` by calling `GET /api/auth/me` with the `X-Tenant` header set to the
just-selected tenant and SHALL set `user.roles` to that tenant's effective (merged global +
per-tenant) roles, so that `MainMenu` gates entries on the new tenant's roles — hiding entries
for roles not held there and showing entries for tenant-scoped roles held there — while
`SysAdmin`-gated entries remain available whenever `SysAdmin` is in the global JWT groups.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

Property 2: Preservation - Non-Switch And Unchanged-Role Behavior

_For any_ input where the bug condition does NOT hold (`isBugCondition` returns false —
single-tenant users, the login/mount resolution path, or a switch that does not change the
effective role set), the fixed code SHALL produce the same result as the original code,
preserving login/mount role resolution, module-flag freshness and compound gating,
`localStorage` persistence and `currentTenant` updates, the App-level module-loss redirect,
and flicker-free rendering of still-valid entries.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Design decision: where the re-resolution lives (least coupling)

The re-resolution must react to `currentTenant` but must not invert the context dependency
graph. Today the direction is **Tenant → Auth**: `TenantContext` imports `useAuth`. If
`AuthContext` subscribed to `currentTenant` it would need to import `useTenant`, creating a
**circular context dependency** (and `AuthProvider` wraps `TenantProvider` in `App.tsx`, so
`AuthContext` cannot call `useTenant` at all).

**Chosen approach — App-level bridge:** `AuthContext` exposes a new imperative action
`refreshRolesForTenant(tenant)` that re-resolves only `user.roles` for an explicitly supplied
tenant. A small effect wired inside `AppContent` (which sits under both providers) reads
`currentTenant` from `useTenant()` and calls `refreshRolesForTenant(currentTenant)` whenever it
changes. This mirrors exactly how `useTenantModules` and `useTenantFunctions` already consume
`currentTenant` at the hook level without inverting the graph, keeps `AuthContext` free of any
`TenantContext` import, and keeps the trigger (tenant) and the state owner (auth) decoupled.

Rejected alternatives:
- _AuthContext subscribes to `currentTenant`_ — impossible/circular given provider nesting and
  the existing Tenant → Auth import.
- _Move roles into TenantContext_ — larger blast radius, breaks `useAuth` consumers, violates
  preservation of the login/mount path.

### Changes Required

**File**: `frontend/src/context/AuthContext.tsx`

**Function**: new `refreshRolesForTenant(tenant: string)` added to the provider and context
value.

**Specific Changes**:
1. **Add a tenant-scoped, roles-only refresh action**: `refreshRolesForTenant(tenant)`
   re-resolves roles for the supplied tenant and updates only `user.roles`
   (via `setUser(prev => prev ? { ...prev, roles } : prev)`), leaving email/name/tenants/sub
   and the mount path untouched. Expose it on `AuthContextValue`.

2. **Explicit-tenant, no-store fetch primitive**: introduce a roles resolver that takes an
   explicit tenant and passes `cache: 'no-store'`, rather than relying on the lagging
   `localStorage` read inside today's `getCurrentUserRoles()`. Preferred implementation: add an
   optional `tenant` parameter (and `no-store` semantics) to
   `getCurrentUserRoles(tenant?: string)` in `authService.ts` so the header is set from the
   argument when provided and from `localStorage` otherwise (login/mount path unchanged). The
   existing JWT `cognito:groups` fallback on non-OK/error is preserved verbatim.

3. **Out-of-order guard**: `refreshRolesForTenant` captures `tenantAtStart = tenant`; after the
   response resolves it applies the result only if the tenant is still current, using the same
   cancelled-flag + `tenantAtStart` comparison pattern as `useTenantModules`. The App-level
   effect returns a cleanup that sets the cancelled flag.

4. **Preserve login/mount**: `checkAuthState()`, its mount `useEffect([])`, and
   `refreshUserRoles()` are unchanged. `refreshUserRoles()` continues to re-run
   `checkAuthState()` for the login flow.

**File**: `frontend/src/App.tsx` (`AppContent`)

**Specific Changes**:
5. **Wire the trigger**: add an effect keyed on `currentTenant` (from `useTenant()`) that calls
   `refreshRolesForTenant(currentTenant)` when a tenant is present, with a cleanup that cancels
   the in-flight resolution. Skip when `currentTenant` is null. This co-locates the role
   refresh with the existing module/function refreshes so all three settle on the same trigger.

**Files NOT changed**: `TenantContext.tsx` (persistence/`currentTenant` untouched),
`MainMenu.tsx` (compound gating untouched — it simply reads the now-fresh `user.roles`),
`useTenantModules.ts` / `useTenantFunctions.ts` (module-flag freshness untouched), backend
`auth_routes.py` (already merges roles and guarantees `SysAdmin`).

### Consistency with the related module-refresh spec (no flicker)

Module flags already refresh on `currentTenant`; this fix adds a role refresh on the same
trigger. Both are gated together in `MainMenu` (`module flag AND role`). To avoid flickering a
valid entry away while one of the two is mid-flight, the role refresh updates `user.roles`
in place (no intermediate clear) and applies the new set atomically only after a successful
response; on failure it falls back to JWT roles rather than emptying the set. A switch that
does not change the effective role set therefore produces no visible change (Requirement 3.5).

## Testing Strategy

### Toolchain

Confirmed from `frontend/package.json`: test runner is **Vitest** (`"test": "vitest"`,
`"test:run": "vitest run"`), with `@testing-library/react`, `@testing-library/jest-dom`,
`jsdom`, `msw` for HTTP mocking, and `fast-check` / `@fast-check/vitest` available for
property-based tests. Run with `cd frontend && npm run test:run` (single-run, non-watch).

### Validation Approach

Two phases: first surface counterexamples on the UNFIXED code (roles do not change on switch),
then verify the fix re-resolves roles correctly and preserves all non-switch behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix, and
confirm the verified root cause (no tenant-keyed role refresh).

**Test Plan**: Render `AuthProvider` + `TenantProvider` (or the `AppContent` bridge) with a
mocked `/api/auth/me` (via `msw`) that returns different effective roles per `X-Tenant`. Drive
a tenant switch through `setCurrentTenant` and assert on `MainMenu` visibility. Run against
unfixed code to observe the failures.

**Test Cases**:
1. **h-dcn reproduction (over-show)**: global roles include `Tenant_Admin`; `/api/auth/me` for
   `h-dcn` omits it. Switch to `h-dcn` → assert `Tenantbeheer` hidden (will fail on unfixed
   code — stays visible).
2. **h-dcn reproduction (under-show)**: `/api/auth/me` for `h-dcn` includes a Members role not
   in the JWT. Switch to `h-dcn` → assert `Leden Overzicht` visible (will fail on unfixed code
   — missing).
3. **No refetch on switch**: assert `/api/auth/me` is called with `X-Tenant: h-dcn` after the
   switch (will fail on unfixed code — never called).

**Expected Counterexamples**:
- `user.roles` unchanged after switch; `MainMenu` gated on previous tenant's roles.
- Possible causes (now confirmed): no `currentTenant`-keyed effect; `refreshUserRoles` login-only.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed code produces the expected
behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := refreshRolesForTenant(input.toTenant)   // updates user.roles
  ASSERT result = effectiveRolesFor(input.toTenant)
     AND ('SysAdmin' IN input.globalRoles) IMPLIES ('SysAdmin' IN result)
     AND menuEntriesGatedBy(result) = expectedEntriesFor(input.toTenant)
END FOR
```

**Test Cases**:
1. **Roles re-resolved (2.1, 2.4)**: after switch, `user.roles` equals `/api/auth/me` roles for
   the new tenant; call made with correct `X-Tenant`.
2. **Over-show hidden (2.2)**: `Tenantbeheer` hidden on `h-dcn`.
3. **Under-show shown (2.3)**: `Leden Overzicht` shown on `h-dcn`.
4. **Freshness / no-store (2.5)**: switch passes the just-selected tenant explicitly and the
   request uses `cache: 'no-store'`; the applied roles come from the fresh response body, not a
   stale/cached one.
5. **Out-of-order guard (2.6)**: fire A → B → C rapidly with A's response delayed to arrive
   last; assert final `user.roles` equals C's effective roles (late A response discarded).
6. **SysAdmin preserved (2.7)**: with `SysAdmin` in global JWT groups, `Systeembeheer` remains
   visible on every tenant; the frontend does not strip `SysAdmin`.
7. **Graceful fallback (2.8)**: `/api/auth/me` returns non-OK / network error → `user.roles`
   falls back to JWT `cognito:groups`; menu is not cleared and no crash.

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed code equals the
original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT F(input) = F'(input)
END FOR
```

**Testing Approach**: Property-based testing (fast-check) is recommended for preservation —
generate random role sets / tenant sequences where the effective set is unchanged and assert
menu output is identical to the unfixed baseline. It exercises many combinations and catches
flicker/edge cases manual tests miss.

**Test Plan**: Capture unfixed-code behavior for single-tenant users, the login/mount path, and
unchanged-role switches, then assert the fixed code reproduces it.

**Test Cases**:
1. **Single-tenant unchanged (3.1)**: one-tenant user renders the same menu as today; no switch
   trigger fires.
2. **Login/mount unchanged (3.2)**: initial `user.roles` populated by `checkAuthState()` exactly
   as before; `refreshUserRoles()` still re-runs `checkAuthState()`.
3. **Module-flag freshness untouched (3.3)**: `useTenantModules`/`useTenantFunctions` still drive
   `hasFIN/hasSTR/hasZZP/hasMEMBERS/hasFunction`; compound gating preserved.
4. **Persistence unchanged (3.4)**: switch still writes `selectedTenant` to `localStorage` and
   updates `currentTenant`.
5. **No flicker on unchanged roles (3.5)**: switching between tenants with an identical
   effective role set produces no removal/re-add of valid entries.
6. **Module-loss redirect unchanged (3.6)**: App.tsx redirect for a page the user can no longer
   access behaves as today.

### Unit Tests

- `refreshRolesForTenant` sets `X-Tenant` to the supplied tenant and updates only `user.roles`.
- `getCurrentUserRoles(tenant?)` uses the argument tenant when provided, `localStorage`
  otherwise; JWT fallback on non-OK/error.
- App-level effect calls `refreshRolesForTenant` on `currentTenant` change and skips when null.
- `no-store` applied on the switch fetch.

### Property-Based Tests

- Generate random `(globalRoles, perTenantRoles, tenantSequence)` and assert final `user.roles`
  equals the last tenant's effective roles and `SysAdmin` is retained iff globally present.
- Generate rapid out-of-order response orderings and assert the last-selected tenant wins.
- Generate unchanged-role switches and assert menu output equals the unfixed baseline
  (preservation / no flicker).

### Integration Tests

- Full flow: login → switch to `h-dcn` → menu reflects `h-dcn` effective roles (`Tenantbeheer`
  gone, `Leden Overzicht` present, `Systeembeheer` still present).
- Switch back to the original tenant → original entries restored.
- Combined module + role settle: after a switch, module flags and roles converge without an
  intermediate frame that drops a still-valid entry.

## Requirements Traceability

| Requirement | Addressed by |
|---|---|
| 1.1–1.4 (defect) | Root cause (no tenant-keyed refresh) + Fix change 1,3,5 |
| 2.1 gate on new tenant roles | Fix 1,5; Fix Checking #1; Integration |
| 2.2 hide over-shown entry | Property 1; Fix Checking #2; Exploratory #1 |
| 2.3 show tenant-scoped entry | Property 1; Fix Checking #3; Exploratory #2 |
| 2.4 call /api/auth/me with X-Tenant | Fix 1,2; Fix Checking #1; Exploratory #3 |
| 2.5 fresh body (no-store) | Fix 2,3; Fix Checking #4 |
| 2.6 out-of-order guard | Fix 3; Fix Checking #5; PBT |
| 2.7 SysAdmin preserved | Backend merge + no frontend strip; Fix Checking #6 |
| 2.8 graceful JWT fallback | Fix 2; Fix Checking #7 |
| 3.1 single-tenant unchanged | Preservation #1 |
| 3.2 login/mount unchanged | Fix 4; Preservation #2 |
| 3.3 module-flag freshness + compound gating | No change to hooks/MainMenu; Preservation #3 |
| 3.4 localStorage persistence | No change to TenantContext; Preservation #4 |
| 3.5 no flicker on unchanged roles | Atomic in-place role update; Preservation #5; PBT |
| 3.6 module-loss redirect unchanged | No change to App redirect; Preservation #6 |
